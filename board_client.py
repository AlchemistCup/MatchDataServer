import asyncio
from uuid import getnode
import argparse
import capnp
import game_capture_capnp

from base_client import Client
from logger import get_logger

def parse_args():
    parser = argparse.ArgumentParser(
        usage="Specify mac address used for fake board client"
    )
    parser.add_argument("mac", type=int)

    return parser.parse_args()

async def main(loop):
    mac = parse_args().mac
    client = FakeBoardClient(loop, mac)
    await client.connect(addr='localhost')

class FakeBoardClient(Client):
    def __init__(self, loop: asyncio.AbstractEventLoop, mac: int):
        self._logger = get_logger(__class__.__name__)
        self._loop = loop
        self._mac = mac # getnode()
        self._data_feed = None
        super().__init__(loop, self._logger)

    async def on_connect(self, server):
        client = BoardImpl(self)
        self._logger.info(f"Registering with server (MAC: {hex(self._mac)})")
        data_feed = (await self.handle_request(server.register(self._mac, {'board': client}), timeout=2.0)).dataFeed

        if data_feed is None:
            self._logger.error('Did not receive registration response')
            return False
        
        match data_feed.which():
            case 'board':
                self._logger.info(f"Registered successfully, reassigned to match")
                self._data_feed = data_feed.board
            case 'rack':
                self._logger.error('Server responded with incompatible data feed to registration request')
                self.disconnect(retry_connection=False)
            case 'none':
                self._logger.info(f"Registered successfully, not assigned to match")

        async def test_send_move():
            while self._retry_task:
                await asyncio.sleep(10)
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
        
        self.add_task(test_send_move)
        return True

    async def on_disconnect(self):
        self._logger.debug("Resetting data feed")
        self._data_feed = None

    async def send_move(self, move):
        assert self._is_connected
        self._logger.info("Sending move to server")
        res = (await self._data_feed.sendMove(move).a_wait()).success
        self._logger.info(f"Obtained response {res} for sendMove")
        return res

class BoardImpl(game_capture_capnp.Board.Server):
    def __init__(self, client: FakeBoardClient):
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