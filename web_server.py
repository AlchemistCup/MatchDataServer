import asyncio
import aiohttp
from aiohttp import web
import logging
from typing import Dict, Any, Tuple

from logger import get_logger
import matchdata as md
from tcp_server import TCPServer
from util import Result

logging.getLogger(aiohttp.__name__).setLevel(logging.WARN) # Disable info logging from aiohttp

class HTTPServer:
    def __init__(self, loop, sensor_server: TCPServer):
        self._loop = loop
        self._logger = get_logger(__class__.__name__)
        self._sensor_server = sensor_server
        self._app = web.Application()
        self._setup_routes()
        self._player_name_to_match_id: Dict[Tuple[str, str], str] = {}

    def _setup_routes(self):
        routes = web.RouteTableDef()

        @routes.get('/setup')
        async def setup_match(request: web.Request):
            p1, p2 = request.query.get('p1'), request.query.get('p2')
            
            self._logger.info(f"Received match setup request with player1 = {p1} and player2 = {p2}")
            
            if (p1, p2) in self._player_name_to_match_id:
                self._logger.info(f"({p1}, {p2}) are already assigned to match {match_id}")
                # TODO: Pass other essential match data back to client
                return self._player_name_to_match_id[(p1, p2)]
            
            match_id = md.GameStateStore().generate_new_match_id()
            error = await self._sensor_server.assign_match(match_id, (p1, p2))
            if error is None:
                self._player_name_to_match_id[(p1, p2)] = match_id
                return HTTPServer._success({"match_id": match_id})
            else:
                return HTTPServer._error(error)
        
        @routes.get('/end-turn')
        async def end_turn(request: web.Request):
            self._logger.debug(f"Received end_turn request {request.query}")

            res = self._validate_request(request)
            if res.is_success:
                game_state = res.value
            else:
                return HTTPServer._error(res.error)

            player_time = request.query.get('player_time')
            res = await game_state.end_turn(player_time)
            if res.is_success:
                return HTTPServer._success(res.value.to_dict())
            else:
                return HTTPServer._error(res.error)

        @routes.get('/challengeable-words')
        async def get_challengeable_words(request: web.Request):
            self._logger.debug(f"Received get_challengeable_words request {request.query}")
            res = self._validate_request(request, turn_modifier=-1)
            if res.is_success:
                game_state = res.value
            else:
                return HTTPServer._error(res.error)
            
            challenge_words = list(game_state.board.get_challenge_words())

            if len(challenge_words) == 0:
                return HTTPServer._error("No challenge words")
            else:
                return self._success({
                    "words": challenge_words
                })
        
        @routes.get('/challenge')
        async def challenge(request: web.Request):
            self._logger.debug(f"Received challenge request {request.query}")

            res = self._validate_request(request)
            if res.is_success:
                game_state = res.value
            else:
                return HTTPServer._error(res.error)
            
            words = request.query.getall('words', [])
            if not words:
                return HTTPServer._error("No challenge words provided")
            elif not all(word in game_state.board.get_challenge_words() for word in words):
                self._logger.error(f'[{match_id}] Received challenge with words {words} that do not match challengable words {game_state.board.get_challenge_words()}')
                return HTTPServer._error("Invalid challenge words")
            
            match_id = request.query.get('match_id')
            self._logger.info(f"[{match_id}] Received challenge request on {words}")

            successful = any(not md.Dictionary().is_valid(word) for word in words)

            previous_score = game_state.board.get_score()

            if successful:
                self._logger.info(f"[{match_id}] Challenge was successful, undoing previous move")
                game_state.board.undo_move()
            
            return HTTPServer._success({
                "successful": successful,
                "challenger_penalty": len(words) * 5,
                "undone_move_score": previous_score
            })
        
        @routes.post('/blanks')
        async def update_blank_tiles(request: web.Request):
            self._logger.debug(f"Received blank tile update {request.query}, has body = {request.can_read_body}")
            body = await request.json()
            self._logger.debug(f"Request body = {body}")

            res = self._validate_request(request, turn_modifier=-1) # Need blanks from previous turn
            if res.is_success:
                game_state = res.value
            else:
                return HTTPServer._error(res.error)
            
            blanks_str = ''.join(body)
            if game_state.board.set_blanks(blanks_str):
                return HTTPServer._success({})
            else:
                return HTTPServer._error("Unable to set blanks")
        
        self._app.add_routes(routes)

    async def start(self):
        runner = web.AppRunner(self._app)
        await runner.setup()
        site = web.TCPSite(runner, host=None, port=9190)  
        await site.start()
        self._logger.info(f"HTTP server listening on port {site._port}")
        await asyncio.Event().wait()

    def _validate_request(self, request: web.Request, turn_modifier: int = 0) -> Result[md.GameState]:
        match_id = request.query.get('match_id')
        turn_number = request.query.get('turn_number')

        try:
            turn_number = int(turn_number)
        except (TypeError, ValueError):
            return Result.failure("Invalid turn number")

        game_state = md.GameStateStore().get_game_state(match_id)
        if game_state is None:
            self._logger.error(f"[{match_id}] Received request which doesn't have associated game state")
            return Result.failure("Invalid match_id")
        elif game_state.turn_number + turn_modifier != turn_number:
            self._logger.error(f"[{match_id}]Received request with turn number {turn_number} that does not match game state turn number {game_state.turn_number} + {turn_modifier}")
            return Result.failure("Turn out of sync")
        
        return Result.success(game_state)

    @staticmethod
    def _error(msg: str) :
        return web.json_response({
            "error": msg
        })

    @staticmethod
    def _success(response: Dict[str, Any]):
        return web.json_response({
            "body": response
        })


if __name__ == '__main__':
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    sensor_server = TCPServer(loop)
    http_server = HTTPServer(loop, sensor_server)
    asyncio.run(http_server.start())