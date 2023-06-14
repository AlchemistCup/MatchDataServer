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
    await client.connect()

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
        data_feed = (await server.register(self._mac, {'rack': client}).a_wait()).dataFeed
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
        while self._is_connected:
            await asyncio.sleep(5)
            if self._data_feed is not None:
                await self.send_rack("Example tiles")

    async def on_disconnect(self):
        self._logger.debug("on_disconnect called - currently unimplemented")
        self._data_feed = None

    async def send_rack(self, tiles):
        assert self._is_connected
        self._logger.debug("Sending move to server")
        res = (await self._data_feed.sendRack(self._match_id, self._player, tiles).a_wait()).success
        self._logger.debug(f"Obtained response {res} for sendMove")
        return res

class RackImpl(game_capture_capnp.Rack.Server):
    def __init__(self, client: FakeRackClient):
        game_capture_capnp.Rack.Server.__init__(self)
        self._client = client
        self._logger = self._client._logger

    def assignMatch(self, matchId, player, **kwargs):
        self._logger.info(f"Assigned to match {matchId} for player {player}")
        self._client._match_id = matchId
        self._client._player = player
        return True

if __name__ == '__main__':
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(main(loop))