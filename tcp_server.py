import asyncio
import logging
import capnp
import game_capture_capnp
from scrabble.board_pos import Pos

from logger import get_logger
import matchdata as md

class TCPServer:
    def __init__(self, loop):
        self._loop = loop
        self._logger = get_logger(__class__.__name__)

    async def handle(self, reader, writer):
        # Log connection
        self._logger.info(f"New connection from {writer.get_extra_info('peername')}")
        md.n_of_requests += 1
        self._logger.info(f"Processed {md.n_of_requests} total requests")
        server = CapnProtoServer(self._logger)
        await server.serve(reader, writer)
        self._logger.inf(f"{writer.get_extra_info('peername')} disconnected")

    async def start(self):
        server = await asyncio.start_server(self.handle, host=None, port=9189)
        addr = server.sockets[0].getsockname()
        self._logger.info(f"TCP server listnening on port {addr[1]}")
        await server.serve_forever()

class MatchServerImpl(game_capture_capnp.MatchServer.Server):
    def __init__(self, logger: logging.Logger):
        self._logger = logger
        self._sensor = None # Will need to pass this up later

    def register(self, macAddr, sensorInterface, **kwargs):
        match sensorInterface.which():
            case 'board':
                self._sensor = sensorInterface.board
                self._logger.info(f"Received registration request from board ({macAddr})")
            case 'rack':
                self._sensor = sensorInterface.rack
                self._logger.info(f"Received registration request from rack ({macAddr})")

        return "TestMatchId"
    

    def pulse(self, **kwargs):
        self._logger.info(f"Received pluse")

    def sendMove(self, matchId: str, move, **kwargs):
        def formatTile(tile):
            return f"Tile '{chr(tile.value)}' @ {Pos(tile.pos.row, tile.pos.col)}" 
        
        move_str = ', '.join(formatTile(tile) for tile in move.tiles)
        self._logger.info(f"[{matchId}] Received move {move_str}")

        return True

    def sendRack(self, matchId: str, player, tiles, **kwargs):
        self._logger.info(f"[{matchId}] Received rack {tiles} for player {player}")

        return True

class CapnProtoServer:
    def __init__(self, logger: logging.Logger):
        self._logger = logger

    async def myreader(self):
        while self._retry:
            try:
                # Must be a wait_for so we don't block on read()
                data = await asyncio.wait_for(
                    self._reader.read(4096),
                    timeout=0.1
                )
            except asyncio.TimeoutError:
                self._logger.debug("myreader timeout.")
                continue
            except Exception as err:
                self._logger.error("Unknown myreader err: %s", err)
                return False
            await self._server.write(data)
        self._logger.debug("myreader done.")
        return True

    async def mywriter(self):
        while self._retry:
            try:
                # Must be a wait_for so we don't block on read()
                data = await asyncio.wait_for(
                    self._server.read(4096),
                    timeout=0.1
                )
                self._writer.write(data.tobytes())
            except asyncio.TimeoutError:
                self._logger.debug("mywriter timeout.")
                continue
            except Exception as err:
                self._logger.error("Unknown mywriter err: %s", err)
                return False
        self._logger.debug("mywriter done.")
        return True
    
    async def serve(self, reader, writer):
        # Start TwoPartyServer using TwoWayPipe (only requires bootstrap)
        self._server = capnp.TwoPartyServer(bootstrap=MatchServerImpl(self._logger))
        self._reader = reader
        self._writer = writer
        self._retry = True

        # Assemble reader and writer tasks, run in the background
        coroutines = [self.myreader(), self.mywriter()]
        tasks = asyncio.gather(*coroutines, return_exceptions=True)

        while True:
            self._server.poll_once()
            # Check to see if reader has been sent an eof (disconnect)
            if self._reader.at_eof():
                self._retry = False
                break
            await asyncio.sleep(0.01)

        # Make wait for reader/writer to finish (prevent possible resource leaks)
        await tasks

if __name__ == "__main__":
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    tcp_server = TCPServer(loop)
    asyncio.run(tcp_server.start())