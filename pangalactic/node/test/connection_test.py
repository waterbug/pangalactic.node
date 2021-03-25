# -*- coding: utf-8 -*-

import websocket as ws

def test(url=None):
    url = url or 'ws://localhost:8080/ws'
    ws.enableTrace(True)
    s = ws.WebSocket()
    try:
        s.connect(url)
        print(s.recv())
        s.close()
    except ws.WebSocketConnectionClosedException:
        print('yes server is there')
    except:
        print('oops, no server')

