import asyncio

from logger import get_logger
import matchdata

class TCPServer:
    def __init__(self, loop):
        self._loop = loop
        self._logger = get_logger(__class__.__name__)


    async def handle(self, reader, writer):
        # Log connection
        self._logger.info(f"New connection from {writer.get_extra_info('peername')}")
        matchdata.n_of_requests += 1
        self._logger.info(f"Processed {matchdata.n_of_requests} total requests")

        while True:
            data = await reader.read(1024)
            if not data:
                break
            # Log data and connection it came from
            self._logger.info(f"Received {data!r} from {writer.get_extra_info('peername')}")
            
        # Close the connection
        self._logger.info(f"Closing connection with {writer.get_extra_info('peername')}")
        writer.close()
        await writer.wait_closed()

    async def start(self):
        server = await asyncio.start_server(self.handle, host=None, port=9189)
        addr = server.sockets[0].getsockname()
        self._logger.info(f"TCP server listnening on port {addr[1]}")
        await server.serve_forever()

if __name__ == "__main__":
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    tcp_server = TCPServer(loop)
    asyncio.run(tcp_server.start())