import asyncio
import socket
from uuid import getnode
import capnp
import game_capture_capnp

class Client:
    def __init__(self, host: str = 'matchdata.alchemist.live', port: int = 9189):
        self._host = host
        self._port = port
        self.reset_data()

    def reset_data(self):
        self._task = None
        self._socket = None
        self._client = None
        self._connected = False
        self._dcp = None
        self._match_id = None

    async def connect(self, loop=None):
        if not loop:
            loop = asyncio.get_event_loop()
        if self.is_connected():
            raise Exception("already connected")
        self.reset_data()

        self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._socket.connect((self._host, self._port))
        self._client = capnp.TwoPartyClient(self._socket)
        self._connected = True

        def on_dc(*args, **kwargs):
            self._connected = False

        self._dcp = self._client.on_disconnect().then(on_dc)
        self._match_server = self._client.bootstrap().cast_as(game_capture_capnp.MatchServer)
        await self._on_connected()

        self._task = loop.create_task(self._run())
        self._loop = loop

    # To be overloaded in derived classes if needed
    async def _on_connected(self):
        pass

    def is_connected(self):
        if self._socket is None:
            return False
        try:
            self._socket.getpeername()
        except OSError:
            return False
        return self._connected

    async def disconnect(self):
        if self.is_connected():
            self._socket.shutdown(socket.SHUT_RDWR)
            self._socket.close()

        capnp.poll_once()

        if self._task is not None:
            await self._task

    async def _run(self):
        while self.is_connected():
            capnp.poll_once()
            await asyncio.sleep(0.1)

class BoardClient(Client):
    def __init__(self):
        super().__init__()
        self._board_interface = self.BoardImpl(self)

    async def register(self):
        match_id = (await self._match_server.register(getnode(), self._board_interface).a_wait()).matchId
        if match_id:
            self._match_id = match_id
            print(f"Registration complete, assigned match_id {match_id}")
        print("Registration complete, have not received match_id yet")

    async def pulse(self):
        await self._match_server.pulse().a_wait()
    
    async def send_move(self, move):
        assert self._match_id is not None

        def to_dict(move):
            return move

        return (await self._match_server.sendMove(self._match_id, to_dict(move)).a_wait()).success
    
    class BoardImpl(game_capture_capnp.MatchServer.Board.Server):
        def __init__(self, board_client):
            self._board = board_client
        
        def assignMatch(self, matchId, **kwargs):
            print(f"Assigned to match {matchId}")
            self._board._match_id = matchId
            return True
        
        def confirmMove(self, move, **kwargs):     
            print(f"Confirming move {move}")
            return True
        
        def getFullBoardState(self, **kwargs):
            print(f"Getting full board state")
            return "Test"
        
# class TestImpl(game_capture_capnp.Board.Server):
#     def __init__(self):
#         self._match_id = ""

#     def assignMatch(self, matchId, **kwargs):
#             print(f"Assigned to match {matchId}")
#             self._match_id = matchId
#             return True
        
#     def confirmMove(self, move, **kwargs):     
#         print(f"Confirming move {move}")
#         return True
    
#     def getFullBoardState(self, **kwargs):
#         print(f"Getting full board state")
#         return "Test"
    
# class RackClient(Client):
#     def __init__(self):
#         super().__init__()

#     async def pulse(self):
#         match_id = (await self._match_server.pulse(getnode(), 'board').a_wait()).matchId
#         if match_id:
#             self._match_id = match_id

#     async def send_rack(self, rack):
#         assert self._match_id is not None

#         def to_dict

async def wait_for_match_id(board_client: BoardClient):
    while board_client._match_id is None:
        print("Waiting for match_id")
        await asyncio.sleep(1)

if __name__ == '__main__':
    board_client = BoardClient()
    asyncio.run(board_client.connect())
    asyncio.run(board_client.register())
    asyncio.run(board_client.pulse())
    asyncio.run(wait_for_match_id(board_client))
    asyncio.run(board_client.send_move(
        {'tiles': [
                {
                    'value': ord('A'),
                    'pos': {'row': 4, 'col': 9}
                },
                {
                    'value': ord('?'),
                    'pos': {'row': 4, 'col': 10}
                }
            ]
        }
    ))