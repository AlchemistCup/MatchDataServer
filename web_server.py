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

        @routes.get('/setup')
        async def setup_match(request: web.Request):
            self._logger.debug(f"Received match setup request with player1 = {request.query.get('p1')} and player2 = {request.query.get('p2')}")
            matchdata.n_of_requests += 1
            self._logger.info(f"Processed {matchdata.n_of_requests} total requests")
            #response = web.json_response({'error': 'Insufficient boards'})
            response = web.json_response({
                "body": {
                    "match_id": "TestMatchId"
                }
            })
            return response
        
        @routes.get('/end-turn')
        async def end_turn(request: web.Request):
            self._logger.debug(f"Received end_turn request {request.query}")
            response = web.json_response({
                "body": {
                    "score": 15,
                    "blanks": 1
                }
            })
            return response

        @routes.get('/challengeable-words')
        async def get_challengeable_words(request: web.Request):
            self._logger.debug(f"Received get_challengeable_words request {request.query}")
            response = web.json_response({
                "body": {
                    "words": ["HELLO", "GOODBYE", "ASDFQGE"]
                }
            })
            return response
        
        @routes.get('/challenge')
        async def challenge(request: web.Request):
            self._logger.debug(f"Received challenge request {request.query}")
            response = web.json_response({
                "body": {
                    "successful": False,
                    "penalty": 0
                }
            })
            return response
        
        @routes.post('/blanks')
        async def update_blank_tiles(request: web.Request):
            self._logger.debug(f"Received blank tile update {request.query}, has body = {request.can_read_body}")
            body = await request.text()
            self._logger.debug(f"Request body = {body}")
            response = web.json_response({
                "body": {}
            })
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