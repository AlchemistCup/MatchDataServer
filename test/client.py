import asyncio
import socket
from uuid import getnode
import capnp
import logging
import test_capnp

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

# async def main():
#     loop = asyncio.new_event_loop()
#     asyncio.set_event_loop(loop)
#     client = Client()
#     await client.connect(loop)
#     await client.call_server()
#     await client.register_client()
#     await asyncio.sleep(10)
#     #await client.call_server()
#     while True:
#         await asyncio.sleep(5)
# # Try using socketreader / socketwriter instead

# class BaseClient:
#     def __init__(self, host: str = 'matchdata.alchemist.live', port: int = 9189):
#         self._host = host
#         self._port = port
#         self.reset_data()

#     def reset_data(self):
#         self._task = None
#         self._socket = None
#         self._client = None
#         self._connected = False
#         self._dcp = None
#         self._match_id = None

#     async def connect(self, loop=None):
#         if not loop:
#             loop = asyncio.get_event_loop()
#         if self.is_connected():
#             raise Exception("already connected")
#         self.reset_data()

#         self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
#         self._socket.connect((self._host, self._port))
#         self._client = capnp.TwoPartyClient(self._socket)
#         self._connected = True

#         def on_dc(*args, **kwargs):
#             self._connected = False

#         self._dcp = self._client.on_disconnect().then(on_dc)
#         await self._on_connected()

#         self._task = loop.create_task(self._run())
#         self._loop = loop

#     # To be overloaded in derived classes if needed
#     async def _on_connected(self):
#         pass

#     def is_connected(self):
#         if self._socket is None:
#             return False
#         try:
#             self._socket.getpeername()
#         except OSError:
#             return False
#         return self._connected

#     async def disconnect(self):
#         if self.is_connected():
#             self._socket.shutdown(socket.SHUT_RDWR)
#             self._socket.close()

#         capnp.poll_once()

#         if self._task is not None:
#             await self._task

#     async def _run(self):
#         while self.is_connected():
#             capnp.poll_once()
#             await asyncio.sleep(0.1)

# class Client(BaseClient):
#     def __init__(self):
#         super().__init__()
#         self._board_interface = self.ClientImpl()

#     async def _on_connected(self):
#         self._server = self._client.bootstrap().cast_as(test_capnp.Server)

#     async def call_server(self):
#         print("Trying to call serverMethod")
#         await self._server.serverMethod().a_wait()
#         print("Called serverMethod successfully")

#     async def register_client(self):
#         print("Trying to call registerClient")
#         await self._server.registerClient(self._board_interface).a_wait()
#         print("Registered client successfully")
    
#     class ClientImpl(test_capnp.Client.Server):
#         def clientMethod(self, **kwargs):
#             print(f"Executing clientMethod")


async def main():
    client = Client()
    await client.connect()

class ClientImpl(test_capnp.Client.Server):
    def __init__(self, client):
        #test_capnp.Client.Server.__init__(self)
        self.client = client

    def clientMethod(self, **kwargs):
        print("Executing client method")

class Client:
    def __init__(self, client_name = 'test'):
        '''
        Initializes socket connection and capnproto schemas

        @param client_name: Name of the client, used for logging/info
        '''
        self.retry_task = None
        self.retry_connection = True
        self.addr = None
        self.port = None
        self.reader = None
        self.writer = None
        self.client = None
        self.server = None
        self.overalltasks = []
        self.loop = None
        self.client_name = client_name
        self.is_connected = False

    def __del__(self):
        '''
        Forceably cancel all async tasks when deleting the object
        '''
        # Make sure we have a reference to the running loop
        if not self.loop:
            self.loop = asyncio.get_event_loop()
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
                logger.debug("socketreader timeout.")
                continue
            except Exception as err:
                logger.error("Unknown socketreader err: %s", err)
                return False
            self.client.write(data)
        logger.debug("socketreader done.")
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
                logger.debug("socketwriter timeout.")
                continue
            except Exception as err:
                logger.error("Unknown socketwriter err: %s", err)
                return False
        logger.debug("socketwriter done.")
        return True

    async def socketwatcher(self):
        '''
        Periodically attempts to make an API call with a timeout to validate
        the server is still alive
        '''
        while self.retry_task:
            try:
                print("Pulsing server")
                await asyncio.wait_for(
                    self.server.serverMethod().a_wait(),
                    timeout=1.0
                )
                logger.debug("Server connection ok.")
                await asyncio.sleep(2)
            except asyncio.TimeoutError:
                logging.debug("Server connection failed, disconnecting.")
                # End other tasks
                self.is_connected = False
                return False
            except Exception as err:
                logger.error("Unknown socketwatcher err: %s", err)
                return False
        logger.debug("socketwatcher done.")
        return True

    async def serverwatcher(self):
        '''
        Processes node list updates
        '''
        try:
            client = ClientImpl(self)
            promise = self.server.registerClient(client)
            await promise.a_wait()
            while self.retry_task:
                await asyncio.sleep(1)
        except Exception as err:
            logger.error("Unknown serverwatcher err: %s", err)
            return False
        logger.debug("serverwatcher done.")
        return True

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
            logger.debug(f"Retrying port connection {self.addr}:{self.port}")
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
        self.server = self.client.bootstrap().cast_as(test_capnp.Server)

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
        logger.debug("socketconnection done.")

    async def connect(self, addr='matchdata.alchemist.live', port=9189):
        '''
        Attempts to reconnect to the secured port
        Will gather keys for interfaces
        '''
        self.addr = addr
        self.port = port
        self.loop = asyncio.get_event_loop()
        logger.info(f"Connecting to {self.addr}:{self.port}")

        # Enable task and connection retries
        self.retry_task = True
        self.retry_connection = True

        # Continue to reconnect until specified to stop
        while self.retry_connection:
            try:
                await self.socketconnection()
            except Exception as err:
                logger.error(f"Unhandled Exception: {err}")
            await asyncio.sleep(1)
            logger.debug("connect retry: %s", self.retry_connection)

        # Remove reference to loop once we finish
        self.loop = None
        logger.debug("Connection ended")

    async def disconnect(self, retry_connection=False):
        '''
        Forceably disconnects the server

        @param retry_connection: If set to True, will attempt to reconnect to server
        '''
        logger.info(f"Disconnecting from {self.addr}:{self.port}")

        # Callback
        await self.on_disconnect()

        # Indicate if we are stopping the connection
        # This needs to be set before ending tasks
        if not retry_connection:
            self.retry_connection = False

        # Gently end tasks (should not delay more than 5 seconds)
        self.retry_task = False
        logger.debug("Tasks open: %s", len(self.overalltasks))
        for index, task in enumerate(self.overalltasks):
            logger.debug("Ending task: %s", index)
            await task

        # Cleanup state
        self.reader = None
        self.writer = None
        self.client = None
        self.server = None

        # Stop retrying connection if specified
        if retry_connection:
            logger.debug("Retrying connection.")
            return
        logger.debug("Stopping client.")

    async def on_connect(self, cap):
        '''
        This callback is meant to be overridden
        It is called on server connection events.
        This may occur if the server restarts, or due to some network issue.

        @param cap: Reference to capnp HidIoServer interface
        @param cap_auth: Reference to capnp HidIo interface
                         (May be set to None, if not authenticated)
        '''

    async def on_disconnect(self):
        '''
        This callback is meant to be overridden
        It is called on server disconnection events.
        This may occur if the server dies, or due to some network issue.
        '''

    def on_nodesupdate(self, nodes):
        '''
        This callback is an asynchronous event by HID-IO Core
        If connected, will return a list of nodes only when the list updates
        '''

    def matchdata_server(self):
        '''
        Returns a reference to the matchdata server interface
        This will be refreshed on each on_connect callback event.
        '''
        return self.server

    def retry_connection_status(self):
        '''
        Returns whether or not connection retry is enabled
        Certain events will turn this off (Ctrl+C, bad auth level)
        Use this to stop the event loop.
        '''
        return self.retry_connection
    

if __name__ == '__main__':
    asyncio.run(main())