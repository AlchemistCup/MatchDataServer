import asyncio
from uuid import getnode
import capnp
import game_capture_capnp

from base_client import Client
from logger import get_logger

async def main(loop):
    client = BoardClient(loop)
    await client.connect()

class BoardClient(Client):
    def __init__(self, loop: asyncio.AbstractEventLoop):
        self._logger = get_logger(__class__.__name__)
        self._loop = loop
        self._data_feed = None
        super().__init__(loop, self._logger)

    async def on_connect(self, server):
        client = BoardImpl(self)
        self._logger.info(f"Registering with server (MAC: {hex(getnode())})")
        data_feed = (await server.register(getnode(), {'board': client}).a_wait())
        print(data_feed)
        match data_feed.which():
            case 'board':
                self._logger.info(f"Registered successfully, reassigned to match")
                self._data_feed = data_feed.board
            case 'rack':
                self._logger.error('Server responded with incompatible data feed to registration request')
                self.disconnect(retry_connection=False)
            case 'none':
                self._logger.info(f"Registered successfully, not assigned to match")

        # For testing
        while self._retry_task:
            await asyncio.sleep(5)
            if self._data_feed is not None:
                await self.send_move(
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
                )

    async def on_disconnect(self):
        self._logger.debug("on_disconnect called - currently unimplemented")
        self._data_feed = None

    async def send_move(self, move):
        assert self._is_connected
        self._logger.debug("Sending move to server")
        res = (await self._data_feed.sendMove(self._match_id, move).a_wait()).success
        self._logger.debug(f"Obtained response {res} for sendMove")
        return res

class BoardImpl(game_capture_capnp.Board.Server):
    def __init__(self, client: BoardClient):
        game_capture_capnp.Board.Server.__init__(self)
        self._client = client
        self._logger = self._client._logger

    def assignMatch(self, dataFeed, **kwargs):
        self._logger.info(f"Assigned to match")
        self._client._data_feed = dataFeed
        return True
    
    def confirmMove(self, move, **kwargs):
        self._logger.info(f"Confirming move {str(move)}")
        return True

    def getFullBoardState(self, **kwargs):
        self._logger.info("Getting full board state")
        return "Example Board State"

if __name__ == '__main__':
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(main(loop))