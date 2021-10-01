(() => {
  const game = {};
  let ws = null;
  const initializeGame = (room) => {
    game.room = {id: room};
    if (ws) {
      ws.close();
      ws = null;
    }
    if (!game.room.id) {
      document.getElementById('offline').innerText = '进入房间';
      return;
    }
    document.getElementById('offline').innerText = '返回主页';
    ws = new WebSocket(`ws://${window.location.host}`);
    ws.onopen = () => {
      ws.send(JSON.stringify({type: 'user.init', user_id: window.currentUserId, room_id: game.room.id}));
    };
    ws.onerror = (_ => {
      console.error('error');
    });
    ws.onclose = (event => {
      if (event.code !== 1000) {
        if (event.code === 3200) {
          alert('您已在新的浏览器窗口中进入了该房间，本页面连接中断！');
        } else {
          alert('网络问题，连接已断开！请刷新页面！');
        }
      }
    });
    const initRoom = (room) => {
      game.room = room;
    };
    const setRoomPlayer = (seat, user = null) => {
      game.room.players[seat] = user;
    };
    const setRoomCreator = (seat = null) => {
      game.room.creator = seat;
    };
    const setPlayerOnline = (seat, online) => {
      game.room.players[seat].online = online;
    };
    const handler = {
      'msg.message': (data) => {
        Message(data.content);
      },
      'room.init': (data) => {
        Message(`欢迎来到房间${data.room.id}`);
        initRoom(data.room);
      },
      'room.user.seat': (data) => {
        Message(`玩家${data.old_seat}换到了位置${data.new_seat}`);
        setRoomPlayer(data.new_seat, game.room.players[data.old_seat]);
        setRoomPlayer(data.old_seat, null);
        if (game.room.creator === data.old_seat) {
          setRoomCreator(data.new_seat);
        }
      },
      'room.user.join': (data) => {
        setRoomPlayer(data.user.seat, data.user);
        if (data.creator) {
          Message(`玩家${data.user.seat}进来了，成为了房主`);
          setRoomCreator(data.user.seat);
        } else {
          Message(`玩家${data.user.seat}进来了`);
        }
      },
      'room.user.quit': (data) => {
        Message(`玩家${data.seat}退出了`);
        setRoomPlayer(data.seat, null);
      },
      'room.creator.quit': (data) => {
        if (data.new_creator_seat) {
          Message(`玩家${data.seat}退出了，玩家${data.new_creator_seat}成为房主`);
          setRoomCreator(data.new_creator_seat);
        } else {
          Message(`玩家${data.seat}退出了，房主空缺`);
          setRoomCreator(null);
        }
        setRoomPlayer(data.seat, null);
      },
      'room.user.leave': (data) => {
        Message(`玩家${data.seat}断线了`);
        setPlayerOnline(data.seat, false);
      },
      'room.user.back': (data) => {
        Message(`玩家${data.seat}回来了`);
        setPlayerOnline(data.seat, true);
      },
      'room.state.start': (data) => {
        Message('游戏开始');
        game.room.state = 1;
      },
      'room.state.end': (data) => {
        Message('游戏结束');
        game.room.state = 999;
      },
    };
    ws.onmessage = (ev => {
      const data = JSON.parse(ev.data);
      const {type} = data;
      if (handler[type]) {
        handler[type](data);
      }
    });
  };
  initializeGame(window.location.pathname.substr(1));
  window.onpopstate = (event) => {
    initializeGame(event.target.location.pathname.substr(1));
  };

})();
  const setOffline = () => {
    window.history.pushState(null, null, '/');
    initializeGame('');
    Message('已退出房间');
  };
  const changeRoom = (room) => {
    room = room.replace(/ /g, '');
    if (!room) {
      alert('请输入房间号，空格会被忽略，房间号不能为空');
    } else {
      window.history.pushState(null, null, `/${room}`);
      initializeGame(room);
    }
  };