import asyncio

from tcp_server import TCPServer
from web_server import HTTPServer
from logger import get_logger

class MatchDataServer:
    def __init__(self, loop):
        self._loop = loop
        self._tcp_server = TCPServer(loop)
        self._http_server = HTTPServer(loop)
        self._logger = get_logger('MainServer')

    async def start(self):
        self._logger.info('Starting MatchDataServer')
        await asyncio.gather(self._tcp_server.start(), self._http_server.start())

if __name__ == '__main__':
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    server = MatchDataServer(loop)
    asyncio.run(server.start())