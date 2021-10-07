import random


class User:
    def __init__(self, id, send, seat=None, room=None):
        self.id = id
        self.send = send
        self.online = True
        self.state = 0
        self.seat = seat
        self.room = room

    @property
    def name(self):
        if self.seat is not None:
            return f'玩家{self.seat}'
        return '访客'

    async def set_online(self, online):
        if self.online != online:
            self.online = online
            if self.room is not None:
                if self.seat is not None:
                    if 0 < self.room.state < 999:
                        # 游戏中，玩家中途离开/回来
                        if self.online:
                            await self.room.send_all({'type': 'room.user.back', 'seat': self.seat}, exclude_user_id=self.id)
                        else:
                            await self.room.send_all({'type': 'room.user.leave', 'seat': self.seat}, exclude_user_id=self.id)
                    elif self.room.state == 0:
                        if not self.online:
                            # 游戏未开始，玩家离开，退出房间
                            await self.room.remove_user(self)
                else:
                    if not self.online:
                        # 访客离开，退出房间
                        await self.room.remove_user(self)

    # async def notice(self, *args, **kwargs):
    #     if self.online:
    #         await send_message(self.send, *args, **kwargs)

    async def send_data(self, data):
        if self.online:
            from server import send_data as origin_send_data
            await origin_send_data(self.send, data)

    async def send_response(self, request_data, data):
        await self.send_data({**data, 'type': f'response.{request_data["_id"]}'})

    async def send_message(self, *args, **kwargs):
        from server import send_message
        if self.online:
            await send_message(self.send, *args, **kwargs)

    def to_dict(self):
        # 为了私密性，用户id不会传输，只传输座位号
        return {
            'seat': self.seat,
            'name': self.name,
            'online': self.online,
            'state': self.state,
            'is_creator': self.room.creator is self,
        }


class Room:
    def __init__(self, id: str, creator: User, mode=1):
        self.id = id
        self.creator = creator
        self.users = {creator.id: creator}
        self.state = 0
        self.mode = mode
        self.game = None

    @property
    def max_seats(self):
        if self.mode == 1:
            # 三人斗地主
            return 3
        if self.mode == 2:
            # 四人斗地主
            return 4

    @property
    def suit(self):
        if self.mode == 1:
            # 三人斗地主
            return 1
        if self.mode == 2:
            # 四人斗地主
            return 2

    def __getitem__(self, item):
        if isinstance(item, str):
            if item in self.users.keys():
                return self.users[item]
        elif isinstance(item, int):
            if item == 0:
                return None
            for user in self.users.values():
                if user.seat == item:
                    return user
        return None

    def __contains__(self, item):
        return item in self.users.keys()

    def add_visitor(self, user):
        user.seat = None
        self.users[user.id] = user

    async def remove_user(self, user):
        if user.seat is not None:
            if self.state == 0:
                del self.users[user.id]
                if len(self.users) == 0:
                    # 房间没人了，不需要通知
                    self.creator = None
                else:
                    if self.creator.id == user.id:
                        for i in range(1, self.max_seats + 1):
                            new_creator = self[i]
                            if new_creator is not None:
                                self.creator = new_creator
                                await self.send_all({'type': 'room.creator.quit', 'seat': user.seat, 'new_creator_seat': i})
                                break
                        else:
                            self.creator = None
                            await self.send_all({'type': 'room.creator.quit', 'seat': user.seat, 'new_creator_seat': None})
                    else:
                        await self.send_all({'type': 'room.user.quit', 'seat': user.seat})
        else:
            del self.users[user.id]

    async def add_user(self, user, chosen_seat=None):
        if self.state == 999:
            return
        seats = self.seats
        if self.state == 0 and 0 < len(seats) < self.max_seats:
            if chosen_seat is not None:
                user.seat = chosen_seat
            else:
                for i in range(1, self.max_seats + 1):
                    if i not in seats:
                        user.seat = i
                        break
            self.users[user.id] = user
            await self.send_all({'type': 'room.user.join', 'seat': user.seat, 'user': user.to_dict()}, exclude_user_id=user.id)
        elif self.state == 0 and len(seats) == 0:
            user.seat = chosen_seat or 1
            self.users[user.id] = user
            self.creator = user
            await self.send_all({'type': 'room.user.join', 'seat': user.seat, 'user': user.to_dict(), 'creator': user.seat}, exclude_user_id=user.id)
        else:
            self.add_visitor(user)

    def start_game(self):
        if self.state == 0:
            self.state = 1
            self.game = Game(self, self.suit)

    async def end_game(self):
        if self.state == 1:
            self.state = 999
            await self.send_all({'type': 'room.state.end'})
            for user in self.users.values():
                if user.online:
                    from server import make_data
                    make_data(user.send, {'type': 'server.close', 'code': 1000}, True)

    @property
    def seats(self):
        return {user.seat: user for user in self.users.values() if user.seat is not None}

    # async def notice_all(self, *args, exclude_user_id=None, **kwargs):
    #     for user in self.users.values():
    #         if user.id != exclude_user_id:
    #             await user.notice(*args, **kwargs)

    async def send_all(self, data, exclude_user_id=None):
        users = [user for user in self.users.values() if user.id != exclude_user_id]
        for user in users:
            await user.send_data(data)

    async def send_players(self, data, exclude_user_id=None):
        users = [user for user in self.users.values() if user.seat is not None and user.id != exclude_user_id]
        for user in users:
            await user.send_data(data)

    async def send_visitors(self, data, exclude_user_id=None):
        users = [user for user in self.users.values() if user.seat is None and user.id != exclude_user_id]
        for user in users:
            await user.send_data(data)

    def to_dict(self):
        # 为了私密性，用户id不会传输，只传输座位号
        return {
            'id': self.id,
            'creator': self.creator and self.creator.seat,
            'players': [self[i].to_dict() if self[i] is not None else None for i in range(0, self.max_seats + 1)],
            'state': self.state,
        }


class Game:
    def __init__(self, room, suit=1):
        self.room = room
        self.state = 1
        self.suit = suit
        self.total = 54 * suit
        self.revealed = []
        self.used = []
        self.player_cards = [[]]
        self.last = [[]]
        self.player_number = room.max_seats
        self.landlord = None
        self.order = []
        for i in range(self.player_number):
            self.player_cards.append([])
            self.last.append([])
        self.deliver_cards()

    def deliver_cards(self):
        if self.room.mode == 1:
            cards = [i for i in range(1, 55)]
            random.shuffle(cards)
            for i in range(1, 4):
                self.player_cards[i].extend(cards[(i - 1) * 17:i * 17])
            self.revealed.extend(cards[51:])
        if self.room.mode == 2:
            cards = [i for i in range(1, 109)]
            random.shuffle(cards)
            for i in range(1, 5):
                self.player_cards[i].extend(cards[(i - 1) * 25:i * 25])
            self.revealed.extend(cards[100:])

    async def reset_game(self):
        self.state = 1
        self.revealed.clear()
        self.used.clear()
        for cards in self.player_cards:
            cards.clear()
        for last in self.last:
            last.clear()
        self.deliver_cards()
        await self.send_game_data({'type': 'game.reset'})

    async def send_game_data(self, data):
        users = [(user, self.to_dict(user)) for user in self.room.users.values()]
        for user, game_data in users:
            await user.send_data({**data, 'game': game_data})

    async def call_landlord(self, user):
        self.state = 2
        self.landlord = user.seat
        self.player_cards[user.seat].extend(self.revealed)
        await self.send_game_data({'type': 'game.landlord', 'seat': user.seat})

    async def drop_card(self, user, cards):
        for card in cards:
            if card in self.used or card not in self.player_cards[user.seat]:
                user.send_message('数据不同步，请刷新页面')
                return
        self.used.extend(cards)
        self.last[user.seat] = [*cards]
        for card in cards:
            self.player_cards[user.seat].remove(card)
        self.order.append(user.seat)
        await self.send_game_data({'type': 'game.drop.card', 'seat': user.seat, 'cards': cards})

    async def withdraw_card(self, user):
        cards = self.last[user.seat]
        for card in cards:
            self.used.remove(card)
        self.player_cards[user.seat].extend(cards)
        self.last[user.seat] = []
        j = None
        for i in range(len(self.order)):
            j = len(self.order) - i - 1
            if self.order[j] == user.seat:
                break
        if j is not None:
            del self.order[j]
        await self.send_game_data({'type': 'game.withdraw.card', 'seat': user.seat})

    def to_dict(self, user):
        return {
            'state': self.state,
            'total': self.total,
            'used': self.used,
            'last': self.last,
            'held': [len(i) for i in self.player_cards],
            'revealed': [] if self.state <= 1 else self.revealed,
            'my': self.player_cards[user.seat] if user.seat is not None else [],
            'landlord': self.landlord,
            'top': self.order[-1] if len(self.order) > 0 else None,
        }
