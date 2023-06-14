import asyncio
import logging

import capnp
import game_capture_capnp

class Client:
    def __init__(self, loop: asyncio.AbstractEventLoop, logger: logging.Logger):
        """
        Base capnproto client class which initializes socket connection and MatchServer schema.

        @param loop: Reference to current event loop
        @param logger: Logger to redirect logs to
        """
        self._retry_task = False
        self._reconnection_attempts = 5
        self._addr = None
        self._port = None
        self._reader = None
        self._writer = None
        self._client = None
        self._server = None
        self._tasks = []
        self._loop = loop
        self._is_connected = False
        self._logger = logger

    def __del__(self):
        '''
        Forceably cancel all async tasks when deleting the object
        '''
        asyncio.ensure_future(self.disconnect(), loop=self._loop)

    async def socketreader(self):
        '''
        Reads from asyncio socket and writes to pycapnp client interface
        '''
        while self._retry_task:
            try:
                # Must be a wait_for in order to give watch_connection a slot
                # to try again
                data = await asyncio.wait_for(
                    self._reader.read(4096),
                    timeout=5.0
                )
            except asyncio.TimeoutError:
                self._logger.debug2("socketreader timeout.")
                continue
            except Exception as err:
                self._logger.error("Unknown socketreader err: %s", err)
                return False
            self._client.write(data)
        self._logger.debug("socketreader done.")
        return True

    async def socketwriter(self):
        '''
        Reads from pycapnp client interface and writes to asyncio socket
        '''
        while self._retry_task:
            try:
                # Must be a wait_for in order to give watch_connection a slot
                # to try again
                data = await asyncio.wait_for(
                    self._client.read(4096),
                    timeout=5.0
                )
                self._writer.write(data.tobytes())
            except asyncio.TimeoutError:
                self._logger.debug2("socketwriter timeout.")
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
        while self._retry_task:
            try:
                self._logger.debug("Pulsing server")
                await asyncio.wait_for(
                    self._server.pulse().a_wait(),
                    timeout=1.0
                )
                self._logger.debug("Server connection ok.")
                await asyncio.sleep(2)
            except asyncio.TimeoutError:
                self._logger.warning("Server connection failed, disconnecting.")
                # End other tasks
                self._is_connected = False
                return False
            except Exception as err:
                self._logger.error("Unknown socketwatcher err: %s", err)
                return False
        self._logger.debug("socketwatcher done.")
        return True

    async def socketconnection(self):
        '''
        Main socket connection function
        May be called repeatedly when trying to open a connection
        '''
        # Make sure we retry tasks on reconnection
        self._retry_task = True

        try:
            self._reader, self._writer = await asyncio.wait_for(
                asyncio.open_connection(self._addr, self._port),
                timeout=1.0
            )
            self._is_connected = True
        except (asyncio.TimeoutError, OSError):
            self._logger.debug(f"Retrying port connection {self._addr}:{self._port}")
            self._reconnection_attempts -= 1
            return False

        self._tasks = []

        # Assemble reader and writer tasks, run in the background
        self._logger.debug("Backgrounding socket reader and writer functions")
        coroutines = [self.socketreader(), self.socketwriter()]
        self._tasks.append(asyncio.gather(*coroutines, return_exceptions=True))

        # Start TwoPartyClient using TwoWayPipe (takes no arguments in this mode)
        self._logger.debug("Starting TwoPartyClient")
        self._client = capnp.TwoPartyClient()
        self._logger.debug("Starting Bootstrap")
        self._server = self._client.bootstrap().cast_as(game_capture_capnp.MatchServer)

        # Start watcher to restart socket connection if it is lost
        self._logger.debug("Backgrounding socketwatcher")
        watcher = [self.socketwatcher()]
        self._tasks.append(asyncio.gather(*watcher, return_exceptions=True))

        # Callback
        await self.on_connect(self._server)
        self._logger.info("Returned from on_connect")

        # Spin here until connection is broken
        while self._is_connected: # Do we update this correctly?
            await asyncio.sleep(1)

        await self.disconnect(retry_connection=True)
        self._logger.debug("socketconnection done.")

    async def connect(self, addr='matchdata.alchemist.live', port=9189):
        '''
        Attempts to reconnect to the secured port
        Will gather keys for interfaces
        '''
        self._addr = addr
        self._port = port
        self._logger.info(f"Connecting to {self._addr}:{self._port}")

        # Enable task and connection retries
        self._retry_task = True

        # Continue to reconnect until specified to stop
        while self._reconnection_attempts > 0:
            try:
                await self.socketconnection()
            except Exception as err:
                self._logger.error(f"Unhandled Exception: {err}")
            await asyncio.sleep(1)
            self._logger.info(f"{self._reconnection_attempts} remaining reconnection attempts")

        # Remove reference to loop once we finish
        self._logger.debug("Connection ended")

    async def disconnect(self, retry_connection=False):
        '''
        Forceably disconnects the server

        @param retry_connection: If set to True, will attempt to reconnect to server
        '''
        self._logger.info(f"Disconnecting from {self._addr}:{self._port}")

        # Callback
        await self.on_disconnect()

        # Indicate if we are stopping the connection
        # This needs to be set before ending tasks
        if not retry_connection:
            self._reconnection_attempts = 0

        # Gently end tasks (should not delay more than 5 seconds)
        self._is_connected = False
        self._retry_task = False
        self._logger.debug(f"Tasks open: {len(self._tasks)}")
        for index, task in enumerate(self._tasks):
            self._logger.debug(f"Ending task {index}")
            await task

        # Cleanup state
        self._reader = None
        self._writer = None
        self._client = None
        self._server = None

        # Stop retrying connection if specified
        if self._reconnection_attempts > 0:
            self._logger.debug("Retrying connection.")
            self._reconnection_attempts -= 1
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
        return self._server