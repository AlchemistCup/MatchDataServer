import asyncio
import logging
from enum import Enum
from typing import Dict, List, Tuple

from logger import get_logger
from util import Singleton
from matchdata import GameStateStore

import capnp
import game_capture_capnp
from scrabble.src.board_pos import Pos

"""
Notes:
- ConnectionHandler should be owned by TCPServer (top-level)
- TCP Server creates a SensorSocket (CapnprotoServer) on connection, which directly manages the sensor it's connected to
    - SensorSocket implements the capnproto MatchServer interface (this interface should be as stateless as possible, and rely on the SensorSocket to manage the state)
    - Also takes a reference to the ConnectionHandler
    - Should *not* require a reference to the TCP Server itself
    - Changes to global gamestate can be made easily
"""

# Names match capnproto enum
class SensorType(Enum):
    board = 1
    rack = 2

class SensorRole(Enum):
    board = 1
    player1 = 2
    player2 = 3

def are_compatible(type: SensorType, role: SensorRole):
    match type:
        case SensorType.board:
            return role == SensorRole.board
        case SensorType.rack:
            return role == SensorRole.player1 or role == SensorRole.player2
        
    assert False, f"Unexpected SensorType {type}"

class TCPServer():
    def __init__(self, loop):
        self._loop = loop
        self._logger = get_logger(__class__.__name__)
        self._connection_handler = ConnectionHandler()

    async def handle(self, reader, writer):
        # Log connection
        self._logger.info(f"New connection from {writer.get_extra_info('peername')}")
        socket = SocketHandler(self._connection_handler, reader, writer)
        await socket.serve()
        self._logger.info(f"{writer.get_extra_info('peername')} disconnected")
        # Handle disconnection here
        self._connection_handler.on_disconnect(socket)

    async def start(self):
        server = await asyncio.start_server(self.handle, host=None, port=9189)
        addr = server.sockets[0].getsockname()
        self._logger.info(f"TCP server listnening on port {addr[1]}")
        await server.serve_forever()

    async def assign_match(self, match_id: str):
        return await self._connection_handler.assign_match(match_id)
    
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

class SocketHandler:
    def __init__(self, connection_handler, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        """
        Base capnproto socket server class which is created when receiving a new connection
        """
        self._connection_handler = connection_handler
        self._logger: logging.Logger = get_logger(__class__.__name__)
        self._peername = writer.get_extra_info('peername')
        self._match_server = self.MatchServerImpl(self)
        self._capnp_server = capnp.TwoPartyServer(bootstrap=self._match_server)
        self._reader = reader
        self._writer = writer
        self._retry = True

    @property
    def sensor_type(self):
        return self._match_server._sensor_type
    
    @property
    def sensor(self):
        return self._match_server._sensor
    
    @property
    def mac_address(self):
        return self._match_server._mac_address
    
    @property
    def is_connected(self):
        return self._retry

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
            #self._logger.debug(f"Size of packet: {len(data)}")
            await self._capnp_server.write(data)
        self._logger.debug2("myreader done.")
        return True

    async def socketwriter(self):
        while self._retry:
            try:
                # Must be a wait_for so we don't block on read()
                data = await asyncio.wait_for(
                    self._capnp_server.read(4096),
                    timeout=1.0
                )
                #self._logger.debug(f"Size of packet: {len(data.tobytes())}")
                self._writer.write(data.tobytes())
            except asyncio.TimeoutError:
                self._logger.debug2("mywriter timeout.")
                continue
            except Exception as err:
                self._logger.error("Unknown mywriter err: %s", err)
                return False
        self._logger.debug2("mywriter done.")
        return True
    
    async def serve(self):
        # Assemble reader and writer tasks, run in the background
        coroutines = [self.socketreader(), self.socketwriter()]
        tasks = asyncio.gather(*coroutines, return_exceptions=True)

        while self._retry:
            self._capnp_server.poll_once()
            # Check to see if reader has been sent an eof (disconnect)
            if self._reader.at_eof():
                self._logger.info(f"{self._peername} disconnected by peer")
                self._retry = False
            await asyncio.sleep(0.01)

        await tasks

    async def disconnect_client(self):
        self._logger.info(f"Disconnecting {self._peername}")
        self._retry = False
        self._writer.close()
        await self._writer.wait_closed()
        self._logger.info(f"Disconnected {self._peername}")

    class MatchServerImpl(game_capture_capnp.MatchServer.Server):
        def __init__(self, socket_handler):
            self._socket_handler = socket_handler
            self._logger: logging.Logger = socket_handler._logger
            self._sensor = None
            self._sensor_type = None
            self._mac_address = None

        # Currently cannot be async - can be once new capnproto update is out
        def register(self, macAddr, sensorInterface, **kwargs):
            self._logger.info(f"Received registration request from {sensorInterface.which()} ({hex(macAddr)})")
            self._sensor_type = SensorType[sensorInterface.which()]
            self._mac_address = macAddr

            match self._sensor_type:
                case SensorType.board:
                    self._sensor = sensorInterface.board
                case SensorType.rack:
                    self._sensor = sensorInterface.rack

            # TODO: Update this to await once using new capnp version
            data_feed = self._socket_handler._connection_handler.register_sensor(self._socket_handler)
            self._logger.info(f'Responding to registration request from {hex(macAddr)} with {data_feed.schema}')
            return data_feed
        
        def pulse(self, **kwargs):
            self._logger.debug(f"Received pluse")


def make_data_feed(match_id, role: SensorRole):
    match role:
        case SensorRole.board:
            return {'board': BoardFeed(match_id)}
        case SensorRole.player1 | SensorRole.player2:
            return {'rack': RackFeed(match_id, role)}
        
    assert False, f"Unexpected role {role}"

class RackFeed(game_capture_capnp.RackFeed.Server):
    def __init__(self, match_id, player: SensorRole):
        assert are_compatible(SensorType.rack, player)
        self._match_id = match_id
        self._player = player
        self._logger = get_logger(__class__.__name__)

    def sendRack(self, tiles, **kwargs):
        self._logger.info(f"[{self._match_id}] Received rack {tiles} for player {self._player}")

        return True
    
class BoardFeed(game_capture_capnp.BoardFeed.Server):
    def __init__(self, match_id):
        self._match_id = match_id
        self._logger = get_logger(__class__.__name__)
    
    def sendMove(self, move, **kwargs):
        def formatTile(tile):
            return f"Tile '{chr(tile.value)}' @ {Pos(tile.pos.row, tile.pos.col)}" 
        
        move_str = ', '.join(formatTile(tile) for tile in move.tiles)
        self._logger.info(f"[{self._match_id}] Received move {move_str}")

        return True

class MatchSensors:
    def __init__(self, board: SocketHandler, p1_rack: SocketHandler, p2_rack: SocketHandler):
        self._sensors: Dict[SensorRole, SocketHandler] = {
            SensorRole.board: board,
            SensorRole.player1: p1_rack,
            SensorRole.player2: p2_rack
        }

    def reconnect_sensor(self, role: SensorRole, sensor: SocketHandler):
        old = self._sensors[role]
        print(f"Old socket status {old.is_connected}, {old.mac_address}")
        if old.is_connected or old.mac_address != sensor.mac_address:
            return False
        
        self._sensors[role] = sensor
        return True

    @property
    def board(self):
        return self._sensors[SensorRole.board]
    
    @property
    def player1(self):
        return self._sensors[SensorRole.player1]
    
    @property
    def player2(self):
        return self._sensors[SensorRole.player2]

class ConnectionHandler():
    def __init__(self):
        self._available_sensors: Dict[SensorType, Dict[int, SocketHandler]] = {SensorType.board: {}, SensorType.rack: {}}
        self._assigned_sensors: Dict[int, Tuple[str, SensorRole]] = {}
        self._active_matches: Dict[str, MatchSensors] = {}
        self._logger = get_logger(__class__.__name__)

    def register_sensor(self, server: SocketHandler):
        mac_addr = server.mac_address
        if mac_addr in self._assigned_sensors:
            match_id, role = self._assigned_sensors[mac_addr]
            if not are_compatible(server.sensor_type, role):
                self._logger.error(f'Received registration request from {hex(mac_addr)} with sensor type clash, previously {role}, now {server.sensor_type}, disconnecting')
                assert False, "Currently unable to disconnect client as method cannot be asynchronous"
                #await server.disconnect_client()
            else:
                if self._active_matches[match_id].reconnect_sensor(role, server):
                    return make_data_feed(match_id, role)
                else:
                    self._logger.error(f'Unable to reconnect sensor {hex(mac_addr)} to match {match_id}, either due to sensor role mismatch or old socket was not cleaned up properly')
        else:
            if mac_addr in self._available_sensors[server.sensor_type]:
                self._logger.error(f'Received duplicate registration request from {hex(mac_addr)}, disconnecting')
                assert False, "Currently unable to disconnect client as method cannot be asynchronous"
            else:
                self._logger.info(f"Registered {server.sensor_type} ({hex(mac_addr)})")
                self._available_sensors[server.sensor_type][mac_addr] = server
        
        return {'none': None}
        

    async def assign_match(self, match_id: str):
        assert match_id not in self._active_matches, f"Match ID {match_id} already used in active match"

        assigned_sensors = False
    
        while not assigned_sensors:
            if len(self._available_sensors[SensorType.board]) < 1:
                self._logger.info("Insufficient available boards, unable to assign match")
                return False
            
            if len(self._available_sensors[SensorType.rack]) < 2:
                self._logger.info("Insufficient available racks, unable to assign match")
                return False
            
            board_socket = self._select_available_sensor(SensorType.board)
            p1_socket = self._select_available_sensor(SensorType.rack)
            p2_socket = self._select_available_sensor(SensorType.rack)
            
            match_assign_coroutines = [
                board_socket.sensor.assignMatch(BoardFeed(match_id)).a_wait(),
                p1_socket.sensor.assignMatch(RackFeed(match_id, SensorRole.player1)).a_wait(),
                p2_socket.sensor.assignMatch(RackFeed(match_id, SensorRole.player2)).a_wait()
            ]
            self._logger.debug(f"[{match_id}] Sending match assignment requests to sensors")
            results = await asyncio.gather(*match_assign_coroutines)
            self._logger.debug(f"[{match_id}] Obtained assignment responses {results}")
            assigned_sensors = all(results) and all([sensor.is_connected for sensor in [board_socket, p1_socket, p2_socket]])

        GameStateStore().create_new_match(match_id, self)

        self._assigned_sensors[board_socket.mac_address] = (match_id, SensorRole.board)
        self._assigned_sensors[p1_socket.mac_address] = (match_id, SensorRole.player1)
        self._assigned_sensors[p2_socket.mac_address] = (match_id, SensorRole.player2)
        self._active_matches[match_id] = MatchSensors(board_socket, p1_socket, p2_socket)
        self._logger.info(f"[{match_id}] Successfully assigned sensors")
        
        return True
    
    def on_disconnect(self, socket):
        mac_addr = socket.mac_address
        sensor_type = socket.sensor_type
        if sensor_type is None or mac_addr is None:
            self._logger.info(f"Unregistered sensor disconnected, type={sensor_type}, mac={mac_addr}")
        elif mac_addr in self._available_sensors[sensor_type]:
            self._logger.info(f"Unassigned sensor disconnected, type={sensor_type}, mac={mac_addr}, removing from available pool")
            del self._available_sensors[sensor_type][mac_addr]
        elif mac_addr in self._assigned_sensors:
            match_id, role = self._assigned_sensors[mac_addr]
            self._logger.warning(f"Active sensor disconnected, mac={mac_addr}, match_id={match_id}, role={role}")
            # Active sensors aren't touched, since state of sockethandler is used to provide error messages
        else:
            self._logger.warning(f"Removing unmanaged socket from ConnectionHandler type={sensor_type}, mac={mac_addr}")
        
    def _select_available_sensor(self, sensor_type: SensorType):
        _, sensor = self._available_sensors[sensor_type].popitem()
        return sensor

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
    logger = get_logger('TEST')
    success = False
    while not success:
        logger.info("Testing assign match")
        success = await server.assign_match("ExampleID")
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