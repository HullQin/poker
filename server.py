from _weakrefset import WeakSet

from constant import DataType
from error import *
from room import Room, User
from daphne.server import Server
from daphne.ws_protocol import WebSocketProtocol
from asyncio import Queue, QueueEmpty
from functools import partial
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
    await send_data(send, {'type': 'room.init', 'room': server_data})
    if user is None:
        raise ActiveDisconnectionError()
    return user, room


async def handle_server_close(data, *args):
    raise ActiveDisconnectionError(data['code'])


async def handle_user_start_game(data, user, room):
    if user.id != room.creator.id:
        return
    await room.start_game()


handler = {
    'server.close': handle_server_close,
    'user.start.game': handle_user_start_game,
}

memory_leak_detector = WeakSet()


async def application(scope, receive: Queue.get, send: partial[Server.handle_reply, WebSocketProtocol]):
    if scope['type'] != 'websocket':
        request = await receive()
        if request['type'] == 'http.request':
            await send({'type': 'http.response.start', 'status': 200})
            await send({'type': 'http.response.body', 'body': html})
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
    except PassiveDisconnectionError:
        pass
    finally:
        if user is not None:
            await user.set_online(False)


with open(os.path.join(os.path.dirname(__file__), 'static', 'index.html'), 'rb') as fp:
    html = fp.read()
