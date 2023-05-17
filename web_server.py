import asyncio
import aiohttp
from aiohttp import web
import logging

from logger import get_logger
import matchdata

logging.getLogger(aiohttp.__name__).setLevel(logging.WARN) # Disable info logging from aiohttp

class HTTPServer:
    def __init__(self, loop):
        self._loop = loop
        self._logger = get_logger(__class__.__name__)
        self._app = web.Application()
        self._setup_routes()

    def _setup_routes(self):
        routes = web.RouteTableDef()

        @routes.get('/start')
        async def start_match(request: web.Request):
            self._logger.info(f"Received match start request with player1 = {request.query.get('p1')} and player2 = {request.query.get('p2')}")
            matchdata.n_of_requests += 1
            self._logger.info(f"Processed {matchdata.n_of_requests} total requests")
            response = web.json_response({'error': 'Insufficient boards'})
            return response
        
        self._app.add_routes(routes)

    async def start(self):
        runner = web.AppRunner(self._app)
        await runner.setup()
        site = web.TCPSite(runner, host=None, port=9190)  
        await site.start()
        self._logger.info(f"HTTP server listening on port {site._port}")
        await asyncio.Event().wait()


if __name__ == '__main__':
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    http_server = HTTPServer(loop)
    asyncio.run(http_server.start())