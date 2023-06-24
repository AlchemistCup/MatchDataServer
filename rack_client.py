import asyncio
from uuid import getnode
import argparse
import capnp
import game_capture_capnp

from base_client import Client
from logger import get_logger

def parse_args():
    parser = argparse.ArgumentParser(
        usage="Specify mac address used for fake rack client"
    )
    parser.add_argument("mac", type=int)

    return parser.parse_args()

async def main(loop):
    mac = parse_args().mac
    client = FakeRackClient(loop, mac)
    await client.connect(addr='localhost')

class FakeRackClient(Client):
    def __init__(self, loop: asyncio.AbstractEventLoop, mac: int):
        self._logger = get_logger(__class__.__name__)
        self._loop = loop
        self._mac = mac # getnode()
        self._data_feed = None
        super().__init__(loop, self._logger)

    async def on_connect(self, server):
        client = RackImpl(self)
        self._logger.info(f"Registering with server (MAC: {hex(self._mac)})")
        res = await self.handle_request(
            server.register(self._mac, {'rack': client}), 
            timeout=2.0
        )

        if res is None:
            self._logger.error('Did not receive registration response')
            return False

        data_feed = res.dataFeed
        match data_feed.which():
            case 'board':
                self._logger.error('Server responded with incompatible data feed to registration request')
                self.disconnect(retry_connection=False)
            case 'rack':
                self._logger.info(f"Registered successfully, reassigned to match")
                self._data_feed = data_feed.rack
            case 'none':
                self._logger.info(f"Registered successfully, not assigned to match")

        # For testing
        async def test_send_rack():
            while self._retry_task:
                await asyncio.sleep(10)
                if self._data_feed is not None:
                    await self.send_rack("tiles"),

        self.add_task(test_send_rack)
        return True

    async def on_disconnect(self):
        self._logger.debug("Resetting data feed")
        self._data_feed = None

    async def send_rack(self, tiles):
        assert self._is_connected
        self._logger.debug2(f"Sending rack {tiles} to server")
        res = await self.handle_request(
            self._data_feed.sendRack(tiles),
            timeout=1.
        )
        if res is None:
            self._logger.error(f"Did not obtain response for sendRack {tiles}")
        else:
            res = res.success
            self._logger.debug2(f"Obtained response {res} for sendRack")
        return res

class RackImpl(game_capture_capnp.Rack.Server):
    def __init__(self, client: FakeRackClient):
        game_capture_capnp.Rack.Server.__init__(self)
        self._client = client
        self._logger = self._client._logger

    def assignMatch(self, dataFeed, **kwargs):
        self._logger.info(f"Assigned to match")
        self._client._data_feed = dataFeed
        return True

if __name__ == '__main__':
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(main(loop))