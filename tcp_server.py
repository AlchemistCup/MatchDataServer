import asyncio
import socket
import logging
import capnp
import game_capture_capnp
import gc
from scrabble.board_pos import Pos

from logger import get_logger
import matchdata as md

class TCPServer:
    def __init__(self, loop):
        self._loop = loop
        self._logger = get_logger(__class__.__name__)
        self._available_sensors = []

    async def handle(self, reader, writer):
        # Log connection
        self._logger.info(f"New connection from {writer.get_extra_info('peername')}")
        md.n_of_requests += 1
        self._logger.info(f"Processed {md.n_of_requests} total requests")
        server = CapnProtoServer(self, reader, writer)
        await server.serve()
        self._logger.info(f"{writer.get_extra_info('peername')} disconnected")

    async def start(self):
        server = await asyncio.start_server(self.handle, host=None, port=9189)
        addr = server.sockets[0].getsockname()
        self._logger.info(f"TCP server listnening on port {addr[1]}")
        await server.serve_forever()

    async def assign_match(self, match_id: str):
        # Currently just being used to test RPC functionality
        if len(self._available_sensors) == 0:
            self._logger.info("No available sensors, unable to assign match")
            return False
        
        sensor = self._available_sensors[-1]
        self._logger.debug(f"Assigning matchId to sensor {sensor.schema}")
        res = (await sensor.assignMatch(match_id).a_wait()).success
        self._logger.debug(f"Obtained matchId assignment response {res}")
        return res
    
    async def confirm_move(self, move):
        # Currently just being used to test RPC functionality
        if len(self._available_sensors) == 0:
            self._logger.info("No available sensors, unable to confirm move")
            return False
        
        sensor = self._available_sensors[-1]
        self._logger.debug(f"Sending confirmMove to sensor {sensor.schema}")
        res = (await sensor.confirmMove(move).a_wait()).success
        self._logger.debug(f"Obtained confirmMove response {res}")
        return res
    
    async def get_full_board_state(self):
        # Currently just being used to test RPC functionality
        if len(self._available_sensors) == 0:
            self._logger.info("No available sensors, unable to confirm move")
            return False
        
        sensor = self._available_sensors[-1]
        self._logger.debug(f"Sending getFullBoardState to sensor {sensor.schema}")
        res = (await sensor.getFullBoardState().a_wait()).boardState
        self._logger.debug(f"Obtained getFullBoardState response {res}")
        return res

    class MatchServerImpl(game_capture_capnp.MatchServer.Server):
        def __init__(self, server):
            self._server = server
            self._logger: logging.Logger = server._logger

        def register(self, macAddr, sensorInterface, **kwargs):
            match sensorInterface.which():
                case 'board':
                    self._server._available_sensors.append(sensorInterface.board)
                    self._logger.info(f"Received registration request from board ({hex(macAddr)})")
                case 'rack':
                    self._server._available_sensors.append(sensorInterface.rack)
                    self._logger.info(f"Received registration request from rack ({hex(macAddr)})")

            return ""
        

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
    def __init__(self, tcp_server: TCPServer, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        """
        Base capnproto socket server class which is created
        """
        self._tcp_server = tcp_server
        self._logger: logging.Logger = self._tcp_server._logger
        self._peername = writer.get_extra_info('peername')
        self._server = capnp.TwoPartyServer(bootstrap=TCPServer.MatchServerImpl(self._tcp_server))
        self._reader = reader
        self._writer = writer
        self._retry = True

    async def socketreader(self):
        while self._retry:
            try:
                # Must be a wait_for so we don't block on read()
                data = await asyncio.wait_for(
                    self._reader.read(4096),
                    timeout=1.0
                )
            except asyncio.TimeoutError:
                self._logger.debug2("myreader timeout.")
                continue
            except Exception as err:
                self._logger.error("Unknown myreader err: %s", err)
                return False
            await self._server.write(data)
        self._logger.debug("myreader done.")
        return True

    async def socketwriter(self):
        while self._retry:
            try:
                # Must be a wait_for so we don't block on read()
                data = await asyncio.wait_for(
                    self._server.read(4096),
                    timeout=1.0
                )
                self._writer.write(data.tobytes())
            except asyncio.TimeoutError:
                self._logger.debug2("mywriter timeout.")
                continue
            except Exception as err:
                self._logger.error("Unknown mywriter err: %s", err)
                return False
        self._logger.debug("mywriter done.")
        return True
    
    async def serve(self):
        # Assemble reader and writer tasks, run in the background
        coroutines = [self.socketreader(), self.socketwriter()]
        tasks = asyncio.gather(*coroutines, return_exceptions=True)

        while True:
            self._server.poll_once()
            # Check to see if reader has been sent an eof (disconnect)
            if self._reader.at_eof():
                self._retry = False
                break
            await asyncio.sleep(0.01)

        self._logger.debug(f"{self._peername} disconnected by peer")
        await tasks

async def test_client_rpc(server: TCPServer):
    await test_assign_match(server)
    while True:
        await server.confirm_move({'tiles': [
                {
                    'value': ord('A'),
                    'pos': {'row': 4, 'col': 9}
                },
                {
                    'value': ord('?'),
                    'pos': {'row': 4, 'col': 10}
                }
            ]
        })
        await asyncio.sleep(5)
        await server.get_full_board_state()
        await asyncio.sleep(5)

async def test_assign_match(server: TCPServer):
    success = False
    while not success:
        success = await server.assign_match("Testing assign match")
        await asyncio.sleep(5)

async def main(loop):
    tcp_server = TCPServer(loop)
    coroutines = [tcp_server.start(), test_client_rpc(tcp_server)]
    tasks = asyncio.gather(*coroutines, return_exceptions=True)
    await tasks

if __name__ == "__main__":
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(main(loop))