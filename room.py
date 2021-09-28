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

    async def send_message(self, *args, **kwargs):
        from server import send_message
        if self.online:
            await send_message(self.send, *args, **kwargs)

    def to_dict(self):
        # 为了私密性，用户id不会传输，只传输座位号
        return {
            'name': self.name,
            'seat': self.seat,
            'online': self.online,
            'state': self.state,
        }


class Room:
    def __init__(self, id: str, creator: User, max_seats=3):
        self.id = id
        self.creator = creator
        self.users = {creator.id: creator}
        self.state = 0
        self.max_seats = max_seats

    def __getitem__(self, item):
        if isinstance(item, str):
            if item in self.users.keys():
                return self.users[item]
        elif isinstance(item, int):
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
            await self.send_all({'type': 'room.user.join', 'seat': user.seat, 'user': user.to_dict(), 'creator': user.seat}, exclude_user_id=user.id)
        else:
            self.add_visitor(user)

    async def change_user_seat(self, user, new_seat):

        old_seat = user.seat
        user.seat = new_seat

    async def start_game(self):
        if self.state == 0:
            self.state = 1
            await self.send_all({'type': 'room.state.start'})

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
            'players': [self[i].to_dict() if self[i] is not None else None for i in range(1, self.max_seats + 1)],
            'state': self.state,
            'max_seats': self.max_seats,
        }
