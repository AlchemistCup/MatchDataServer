import capnp
import asyncio
import socket
import time
import test_capnp

client_interface = None

async def main():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    server = Server(loop)
    await server.start()

async def try_call_client_method():
    global client_interface
    while True:
        print("Trying to call clientMethod")
        if client_interface is not None:
            print("Calling clientMethod")
            try:
                await asyncio.wait_for(
                    client_interface.clientMethod().a_wait(),
                    timeout=1.0
                )
                print("Called clientMethod")
            except asyncio.TimeoutError:
                print("Error: Call to clientMethod timed out")
        await asyncio.sleep(5)

class Server():
    def __init__(self, loop: asyncio.BaseEventLoop):
        self.loop = loop

    async def start(self):
        server = await asyncio.start_server(self.handle_client, host=None, port=9189)
        await server.serve_forever()

    async def handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        client_address = writer.get_extra_info('peername')
        print(f"New connection from {client_address}")
        server = BaseServer(self)
        serve_task = server.serve(reader, writer)
        talk_to_client_task = try_call_client_method()
        tasks = [serve_task, talk_to_client_task]
        await asyncio.gather(*tasks)
        print(f"Client {client_address} disconnected")

    class ServerImpl(test_capnp.Server.Server):
        def serverMethod(self, **kwargs):
            print("Executing serverMethod")

        def registerClient(self, clientInterface, **kwargs):
            global client_interface
            print("Registering client interface")
            client_interface = clientInterface

# class BaseClient():
#     def __init__(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
#         self._reader = reader
#         self._writer = writer
#         self._retry_task = True
#         self._tasks = []
#         coroutines = [self.socketreader(), self.socketwriter()]
#         self._tasks.append(asyncio.gather(*coroutines, return_exceptions=True))
#         self._client = capnp.TwoPartyClient()
#         self._client_interface = self._client.bootstrap().cast_as(test_capnp.Client)

#     async def socketreader(self):
#         """
#         Reads from asyncio socket and writes to pycapnp client interface
#         """
#         data = await self._reader.read(4096)
#         client.write(data)

#     async def socketwriter(self):
#         """
#         Reads from pycapnp client interface and writes to asyncio socket
#         """
#         while True:
#             data = await self._client.read(4096)
#             self._writer.write(data.tobytes())
#             await self._writer.drain()

    

class BaseServer():
    def __init__(self, server: Server) -> None:
        self._server = server
        self._capnp_server = None
        self._reader: asyncio.StreamReader = None
        self._writer: asyncio.StreamWriter = None
    
    # Copied from documentation
    async def serve(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        self._capnp_server = capnp.TwoPartyServer(bootstrap=Server.ServerImpl())
        self._reader = reader
        self._writer = writer
        self._retry = True

        # Assemble reader and writer tasks, run in the background
        coroutines = [self.socketreader(), self.socketwriter()]
        tasks = asyncio.gather(*coroutines, return_exceptions=True)

        while True:
            self._capnp_server.poll_once()
            # Check to see if reader has been sent an eof (disconnect)
            if self._reader.at_eof():
                self._retry = False
                break
            await asyncio.sleep(0.01)

        # Make wait for reader/writer to finish (prevent possible resource leaks)
        await tasks

    async def socketreader(self):
        while self._retry:
            try:
                # Must be a wait_for so we don't block on read()
                data = await asyncio.wait_for(
                    self._reader.read(4096),
                    timeout=0.1
                )
            except asyncio.TimeoutError:
                #self._logger.debug("myreader timeout.")
                continue
            except Exception as err:
                print("Unknown myreader err: %s", err)
                return False
            # if (data):
            #     print(f"socketreader got {data}")
            await self._capnp_server.write(data)
        #self._logger.debug("myreader done.")
        return True

    async def socketwriter(self):
        while self._retry:
            try:
                # Must be a wait_for so we don't block on read()
                data = await asyncio.wait_for(
                    self._capnp_server.read(4096),
                    timeout=0.1
                )
                # if data:
                #     print(f"socketwriter got {data}")
                self._writer.write(data.tobytes())
            except asyncio.TimeoutError:
                #self._logger.debug("mywriter timeout.")
                continue
            except Exception as err:
                print("Unknown mywriter err: %s", err)
                return False
        #self._logger.debug("mywriter done.")
        return True

if __name__ == '__main__':
    asyncio.run(main())