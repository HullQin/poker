from _weakrefset import WeakSet
from error import *
from room import Room, User
from asyncio import QueueEmpty
import json
import os


class Data:
    rooms = {}


async def close_websocket(send, code=1000):
    await send({'type': 'websocket.close', 'code': code})


async def send_data(send, data):
    await send({'type': 'websocket.send', 'text': json.dumps(data)})


async def receive_and_parse(receive):
    event = await receive()
    if event['type'] == 'websocket.disconnect':
        raise PassiveDisconnectionError()
    try:
        return json.loads(event['text'])
    except json.JSONDecodeError:
        raise ActiveDisconnectionError()


def make_data(send, data, clear=False):
    queue = send.args[0].application_queue
    if clear:
        try:
            while True:
                queue.get_nowait()
        except QueueEmpty:
            pass
    queue.put_nowait({"type": "websocket.receive", "text": json.dumps(data)})


async def init_connect(receive, send):
    event = await receive()
    if event['type'] != 'websocket.connect':
        raise ActiveDisconnectionError()
    await send({'type': 'websocket.accept'})


async def send_message(send, content: str, method: str = 'message'):
    data = {
        'type': f'msg.{method}',
        'content': content,
    }
    await send_data(send, data)


async def init_exchange_data(receive, send):
    data = await receive_and_parse(receive)
    if data['type'] != 'user.init':
        raise ActiveDisconnectionError()
    user_id = data['user_id']
    room_id = data['room_id']
    if room_id in Data.rooms:
        room: Room = Data.rooms[room_id]
        if room.state != 999:
            if user_id in room:
                user = room[user_id]
                if user.online:
                    # 同一账号进入，踢掉另一个人
                    make_data(user.send, {'type': 'server.close', 'code': 3200}, True)
                else:
                    # 重新上线
                    await user.set_online(True)
                user.send = send
            else:
                user = User(id=user_id, send=send, room=room)
                await room.add_user(user)
        else:
            user = None
    else:
        user = User(id=user_id, send=send, seat=1)
        room = Room(id=room_id, creator=user)
        user.room = room
        Data.rooms[room_id] = room
    server_data = room.to_dict()
    if room.state == 1:
        await send_data(send, {'type': 'room.init', 'room': server_data, 'seat': user.seat, 'game': room.game.to_dict(user)})
    else:
        await send_data(send, {'type': 'room.init', 'room': server_data, 'seat': user.seat})

    if user is None:
        raise ActiveDisconnectionError()
    return user, room


async def handle_server_close(data, *args):
    raise ActiveDisconnectionError(data['code'])


async def handle_user_start_game(data, user, room):
    if user.id != room.creator.id:
        await user.send_response(data, {'content': '您不是房主，没有权限开始游戏'})
        return
    if room.state != 0:
        await user.send_response(data, {'content': '本房间的游戏已经开始了'})
        return
    room.start_game()
    await user.send_response(data, {'ok': True})
    await room.game.send_game_data({'type': 'room.state.start'})


async def handle_user_seat_change(data, user, room):
    if user.seat == data['seat']:
        return
    if room.state != 0:
        await user.send_message('游戏已开始，不能切换座位')
    elif data['seat'] is None:
        await room.remove_user(user)
        await room.add_visitor(user)
    elif room[data['seat']] is not None:
        await user.send_message(f'位置{data["seat"]}已经被抢了')
    elif user.seat is None:
        await room.add_user(user, data['seat'])
        await user.send_data({'type': 'room.user.seat', 'old_seat': None, 'user': user.to_dict(), 'is_me': True})
    else:
        old_seat = user.seat
        user.seat = data['seat']
        await user.send_data({'type': 'room.user.seat', 'old_seat': old_seat, 'user': user.to_dict(), 'is_me': True})
        await room.send_all({'type': 'room.user.seat', 'old_seat': old_seat, 'user': user.to_dict()}, exclude_user_id=user.id)


async def handle_user_call_landlord(data, user, room):
    if user.seat is None or room.state != 1 or room.game.state != 1:
        await user.send_message(f'地主被别人抢了')
        return
    await room.game.call_landlord(user)


async def handle_user_drop_card(data, user, room):
    if user.seat is None or room.state != 1 or room.game.state != 2:
        return
    await room.game.drop_card(user, data['cards'])


async def handle_user_withdraw_card(data, user, room):
    if user.seat is None or room.state != 1 or room.game.state != 2 or len(room.game.last[user.seat]) == 0:
        return
    await room.game.withdraw_card(user)


async def handle_user_reset_game(data, user, room):
    if room.creator is not user:
        return
    await room.game.reset_game()


async def handle_user_change_mode(data, user, room):
    if room.creator is not user or room.state != 0:
        return
    # room.mode = data['mode']
    if room.mode == 2:
        room.mode = 1
        if room[4] is not None:
            make_data(room[4].send,  {'type': 'server.close', 'code': 3001}, True)
    else:
        room.mode = 2
    await room.send_all({'type': 'room.init', 'room': room.to_dict()}, exclude_user_id=room[4] and room[4].id)


handler = {
    'server.close': handle_server_close,
    'user.start.game': handle_user_start_game,
    'user.seat.change': handle_user_seat_change,
    'user.call.landlord': handle_user_call_landlord,
    'user.drop.card': handle_user_drop_card,
    'user.withdraw.card': handle_user_withdraw_card,
    'user.reset.game': handle_user_reset_game,
    'user.change.mode': handle_user_change_mode,
}

memory_leak_detector = WeakSet()
files = {}
STATIC = os.path.join(os.path.dirname(__file__), 'static')
DEBUG = False


async def application(scope, receive, send):
    if scope['type'] != 'websocket':
        if scope['type'] == 'http':
            if scope['method'] == 'GET':
                if scope['path'].startswith('/static/'):
                    path = scope['path'][1:]
                else:
                    path = 'index.html'
                if not DEBUG and path in files:
                    body = files[path]
                else:
                    filepath = os.path.join(STATIC, path)
                    if os.path.isfile(filepath):
                        with open(filepath, 'rb') as fp:
                            files[path] = fp.read()
                        body = files[path]
                    else:
                        body = None
                if body is not None:
                    if path == 'index.html':
                        headers = []
                    else:
                        headers = [(b'Cache-Control', b'max-age=31536000')]
                    await send({'type': 'http.response.start', 'status': 200, 'headers': headers})
                    await send({'type': 'http.response.body', 'body': body})
                else:
                    send.args[0].basic_error(404, b'Not Found', 'Not Found')
            else:
                send.args[0].basic_error(405, b'Method Not Allowed', 'Method Not Allowed')
        return

    # 首个建立连接的请求
    await init_connect(receive, send)
    # 传输必要数据
    user = None
    try:
        user, room = await init_exchange_data(receive, send)
        memory_leak_detector.add(user)
        while True:
            data = await receive_and_parse(receive)
            if data['type'] in handler:
                await handler[data['type']](data, user, room)
    except ActiveDisconnectionError as e:
        await close_websocket(send, e.args[0])
        if user is not None and e.args[0] != 3200:
            await user.set_online(False)
    except PassiveDisconnectionError:
        if user is not None:
            await user.set_online(False)
