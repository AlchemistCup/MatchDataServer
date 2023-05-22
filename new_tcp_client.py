import asyncio
import socket
from uuid import getnode
import capnp
import logging
import game_capture_capnp

from logger import get_logger

async def main(loop):
    client = BoardClient(loop)
    await client.connect()

class Client:
    def __init__(self, loop: asyncio.AbstractEventLoop, logger: logging.Logger):
        '''
        Base capnproto client class which initializes socket connection and MatchServer schema.

        @param logger: Logger to redirect logs to
        '''
        self.retry_task = None
        self.reconnection_attempts = 5
        self.addr = None
        self.port = None
        self.reader = None
        self.writer = None
        self.client = None
        self.server = None
        self.overalltasks = []
        self.loop = loop
        self.is_connected = False
        self._logger = logger

    def __del__(self):
        '''
        Forceably cancel all async tasks when deleting the object
        '''
        asyncio.ensure_future(self.disconnect(), loop=self.loop)

    async def socketreader(self):
        '''
        Reads from asyncio socket and writes to pycapnp client interface
        '''
        while self.retry_task:
            try:
                # Must be a wait_for in order to give watch_connection a slot
                # to try again
                data = await asyncio.wait_for(
                    self.reader.read(4096),
                    timeout=5.0
                )
            except asyncio.TimeoutError:
                self._logger.debug("socketreader timeout.")
                continue
            except Exception as err:
                self._logger.error("Unknown socketreader err: %s", err)
                return False
            self.client.write(data)
        self._logger.debug("socketreader done.")
        return True

    async def socketwriter(self):
        '''
        Reads from pycapnp client interface and writes to asyncio socket
        '''
        while self.retry_task:
            try:
                # Must be a wait_for in order to give watch_connection a slot
                # to try again
                data = await asyncio.wait_for(
                    self.client.read(4096),
                    timeout=5.0
                )
                self.writer.write(data.tobytes())
            except asyncio.TimeoutError:
                self._logger.debug("socketwriter timeout.")
                continue
            except Exception as err:
                self._logger.error("Unknown socketwriter err: %s", err)
                return False
        self._logger.debug("socketwriter done.")
        return True

    async def socketwatcher(self):
        '''
        Periodically attempts to make an API call with a timeout to validate
        the server is still alive
        '''
        while self.retry_task:
            try:
                self._logger.debug("Pulsing server")
                await asyncio.wait_for(
                    self.server.pulse().a_wait(),
                    timeout=1.0
                )
                self._logger.debug("Server connection ok.")
                await asyncio.sleep(2)
            except asyncio.TimeoutError:
                self._logger.warning("Server connection failed, disconnecting.")
                # End other tasks
                self.is_connected = False
                return False
            except Exception as err:
                self._logger.error("Unknown socketwatcher err: %s", err)
                return False
        self._logger.debug("socketwatcher done.")
        return True

    async def serverwatcher(self):
        '''
        This task is meant to be overridden.
        It handles registering the client interface and handling RPC requests from the server.
        It is called on server connection events.
        This may occur if the server restarts, or due to some network issue.
        '''
        pass

    async def socketconnection(self):
        '''
        Main socket connection function
        May be called repeatedly when trying to open a connection
        '''
        # Make sure we retry tasks on reconnection
        self.retry_task = True

        try:
            self.reader, self.writer = await asyncio.wait_for(
                asyncio.open_connection(self.addr, self.port),
                timeout=1.0
            )
            self.is_connected = True
        except (asyncio.TimeoutError, OSError):
            self._logger.debug(f"Retrying port connection {self.addr}:{self.port}")
            self.reconnection_attempts -= 1
            return False

        self.overalltasks = []

        # Assemble reader and writer tasks, run in the background
        logging.debug("Backgrounding socket reader and writer functions")
        coroutines = [self.socketreader(), self.socketwriter()]
        self.overalltasks.append(asyncio.gather(*coroutines, return_exceptions=True))

        # Start TwoPartyClient using TwoWayPipe (takes no arguments in this mode)
        logging.debug("Starting TwoPartyClient")
        self.client = capnp.TwoPartyClient()
        logging.debug("Starting Bootstrap")
        self.server = self.client.bootstrap().cast_as(game_capture_capnp.MatchServer)

        # Start watcher to restart socket connection if it is lost
        logging.debug("Backgrounding socketwatcher")
        watcher = [self.socketwatcher()]
        self.overalltasks.append(asyncio.gather(*watcher, return_exceptions=True))

        # Start watcher for callbacks from server
        logging.debug("Registering client and backgrounding server callbacks")
        background_tasks = [self.serverwatcher()]
        self.overalltasks.append(asyncio.gather(*background_tasks, return_exceptions=True))

        # Callback
        await self.on_connect(self.server)

        # Spin here until connection is broken
        while self.is_connected:
            await asyncio.sleep(1)

        await self.disconnect(retry_connection=True)
        self._logger.debug("socketconnection done.")

    async def connect(self, addr='matchdata.alchemist.live', port=9189):
        '''
        Attempts to reconnect to the secured port
        Will gather keys for interfaces
        '''
        self.addr = addr
        self.port = port
        self._logger.info(f"Connecting to {self.addr}:{self.port}")

        # Enable task and connection retries
        self.retry_task = True

        # Continue to reconnect until specified to stop
        while self.reconnection_attempts > 0:
            try:
                await self.socketconnection()
            except Exception as err:
                self._logger.error(f"Unhandled Exception: {err}")
            await asyncio.sleep(1)
            self._logger.info(f"{self.reconnection_attempts} remaining reconnection attempts")

        # Remove reference to loop once we finish
        self._logger.debug("Connection ended")

    async def disconnect(self, retry_connection=False):
        '''
        Forceably disconnects the server

        @param retry_connection: If set to True, will attempt to reconnect to server
        '''
        self._logger.info(f"Disconnecting from {self.addr}:{self.port}")

        # Callback
        await self.on_disconnect()

        # Indicate if we are stopping the connection
        # This needs to be set before ending tasks
        if not retry_connection:
            self.reconnection_attempts = 0

        # Gently end tasks (should not delay more than 5 seconds)
        self.retry_task = False
        self._logger.debug(f"Tasks open: {len(self.overalltasks)}")
        for index, task in enumerate(self.overalltasks):
            self._logger.debug(f"Ending task {index}")
            await task

        # Cleanup state
        self.reader = None
        self.writer = None
        self.client = None
        self.server = None

        # Stop retrying connection if specified
        if self.reconnection_attempts > 0:
            self._logger.debug("Retrying connection.")
            self.reconnection_attempts -= 1
            return
        self._logger.debug("Stopping client.")

    async def on_connect(self, server):
        '''
        This callback is meant to be overridden.
        It is called on server connection events.
        This may occur if the server restarts, or due to some network issue.

        @param server: Reference to capnp MatchServer interface
        '''
        pass

    async def on_disconnect(self):
        '''
        This callback is meant to be overridden
        It is called on server disconnection events.
        This may occur if the server dies, or due to some network issue.
        '''
        pass

    @property
    def matchdata_server(self):
        '''
        Returns a reference to the capnp matchdata server interface.
        '''
        return self.server
    
class BoardClient(Client):
    def __init__(self, loop: asyncio.AbstractEventLoop):
        self._logger = get_logger(__class__.__name__)
        self._loop = loop
        super().__init__(loop, self._logger)

    async def serverwatcher(self):
        try:
            client = BoardImpl(self)
            promise = self.server.register(getnode(), {'board': client})
            await promise.a_wait()
            while self.retry_task:
                await asyncio.sleep(1)
        except Exception as err:
            self._logger.error("Unknown serverwatcher err: %s", err)
            return False
        self._logger.debug("serverwatcher done.")
        return True

    async def on_connect(self, server):
        self._logger.debug("on_connect called - currently unimplemented")

    async def on_disconnect(self):
        self._logger.debug("on_disconnect called - currently unimplemented")

class BoardImpl(game_capture_capnp.Board.Server):
    def __init__(self, client: BoardClient):
        game_capture_capnp.Board.Server.__init__(self)
        self._client = client
        self._logger = self._client._logger

    def assignMatch(self, matchId, **kwargs):
        self._logger.info(f"Assigned to match {matchId}")
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