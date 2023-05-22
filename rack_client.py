import asyncio
from uuid import getnode
import capnp
import game_capture_capnp

from base_client import Client
from logger import get_logger

async def main(loop):
    client = RackClient(loop)
    await client.connect()

class RackClient(Client):
    def __init__(self, loop: asyncio.AbstractEventLoop):
        self._logger = get_logger(__class__.__name__)
        self._loop = loop
        super().__init__(loop, self._logger)

    async def on_connect(self, server):
        client = RackImpl(self)
        self._logger.info(f"Registering with server (MAC: {hex(getnode())})")
        self._match_id = (await self._server.register(getnode(), {'rack': client}).a_wait()).matchId
        self._logger.info(f"Registered successfully, server responded with matchId {self._match_id}")

        # For testing
        await asyncio.sleep(5)
        await self.send_rack("Example tiles")

    async def on_disconnect(self):
        self._logger.debug("on_disconnect called - currently unimplemented")

    async def send_rack(self, tiles):
        assert self._is_connected
        self._logger.debug("Sending move to server")
        res = (await self._server.sendRack(self._match_id, self._player, tiles).a_wait()).success
        self._logger.debug(f"Obtained response {res} for sendMove")
        return res

class RackImpl(game_capture_capnp.Rack.Server):
    def __init__(self, client: RackClient):
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