from enum import Enum
from pathlib import Path
from typing import Dict, Tuple, List

from util import Singleton
from logger import get_logger

from tile_bag import TileBag
from rack_delta_resolver import RackDeltaResolver
from board_delta_resolver import BoardDeltaResolver

from scrabble.src.board_pos import Pos
from scrabble.src.board import Board
from scrabble.src.tile import Tile
from scrabble.src.move import Move

CSW21_PATH = Path(__file__).resolve().parent / 'CSW21.txt'

n_of_requests = 0
test = 1

class SensorRole(Enum):
    board = 1
    player1 = 2
    player2 = 3

    @property
    def opposite(self):
        match self:
            case SensorRole.board:
                return SensorRole.board
            case SensorRole.player1:
                return SensorRole.player2
            case SensorRole.player2:
                return SensorRole.player1

class GameStateStore(metaclass=Singleton):
    def __init__(self):
        self._game_state_mapping: Dict[str, GameState] = {}

    def create_new_match(self, match_id, connection_handler):
        assert match_id not in self._game_state_mapping, f"Cannot start new match with match_id={match_id}, this id is already taken"

        self._game_state_mapping[match_id] = GameState(match_id, connection_handler)

    def get_game_state(self, match_id):
        return self._game_state_mapping.get(match_id)

class GameState():
    def __init__(self, match_id, connection_handler) -> None:
        self._match_id = match_id
        self._connection_handler = connection_handler
        self._bag = TileBag()
        self._board = Board()
        self._logger = get_logger(f'{__class__.__name__}-{match_id}')
        self._delta_resolvers = {
            SensorRole.board: BoardDeltaResolver(self._board, self._logger),
            SensorRole.player1: RackDeltaResolver(self._bag, self._logger),
            SensorRole.player2: RackDeltaResolver(self._bag, self._logger)
        }    
        self._turn_n = 0

    def process_delta(self, role: SensorRole, delta):
        resolver = self._delta_resolvers.get(role)
        res = resolver.process_delta(delta) 

        # Handle player 1 drawing during their turn at start of match
        if (self._turn_n == 0 
                and role == SensorRole.player1
                and resolver.n_of_tiles == 7):
            self._logger.info(f'Player 1 finished drawing tiles at start of game')
            if not resolver.end_turn():
                self._logger.error(f"Player 1's rack was invalid after drawing at the start of game - should be impossible (rack={resolver.current_rack})")
            else:
                self._logger.info(f"Confirmed player 1's initial rack state {resolver.current_rack}")
                # TODO: Propagate update to Woogles

        return res
    
    async def end_turn(self):
        drawing_rack_resolver = self._get_drawing_rack()
        # Currently, this partially duplicates the end_turn logic in RackDeltaResolver, which is why this check needs to be done first. Potentially could be nicer to warn players of this before the end of the turn.
        if drawing_rack_resolver.n_of_tiles > 7:
            # TODO: Communicate info to players
            self._logger.error(f"Player {self._get_playing_player().opposite} drew too many tiles ({drawing_rack_resolver.n_of_tiles}). Rack state = {drawing_rack_resolver.current_rack}")
            return False

        playing_rack_delta = self._get_playing_rack().delta
        board_delta = self._board_resolver.delta

        if any(not resolver.end_turn() for resolver in self._delta_resolvers.values()):
            self._logger.error("Unable to resolve end of turn deltas due to resolver error")
            return False
        
        n_of_tiles_from_rack = sum(count for count in playing_rack_delta.values())
        n_of_tiles_played = len(board_delta)
        if n_of_tiles_from_rack > 0 and n_of_tiles_played == 0:
            self._logger.info(f"Player {self._get_playing_player()} exchanged tiles {playing_rack_delta}")
            # TODO: Send info to Woogles
        elif n_of_tiles_from_rack == 0 and n_of_tiles_played == 0:
            self._logger.info(f"Player {self._get_playing_player()} passed")
            # TODO: Send info to Woogles
        elif GameState._resolve_deltas(playing_rack_delta, board_delta):
            move = BoardDeltaResolver.delta_to_move(board_delta)
            self._logger.info(f"Player {self._get_playing_player()} played move {move}")
            await self._connection_handler.confirm_move(self._match_id, move)
            # TODO: Send info to Woogles
        else:
            self._logger.error(f"Could not resolve rack play delta {playing_rack_delta} and tiles in board delta {board_delta}")
            return False
        
        self._turn_n += 1        
        self._logger.info(f"Board State:\n{self._board}")
        self._logger.info(f"P1 Rack State: {self._delta_resolvers[SensorRole.player1].current_rack}")
        self._logger.info(f"P2 Rack State: {self._delta_resolvers[SensorRole.player2].current_rack}")

        # TODO: Send rack info to woogles

    @property
    def _board_resolver(self) -> BoardDeltaResolver:
        return self._delta_resolvers[SensorRole.board]
    
    def _get_playing_player(self):
        return SensorRole.player2 if self._turn_n % 2 else SensorRole.player1

    def _get_playing_rack(self) -> RackDeltaResolver:
        return self._delta_resolvers[self._get_playing_player()]
    
    def _get_drawing_rack(self) -> RackDeltaResolver:
        return self._delta_resolvers[self._get_playing_player().opposite]
    
    @staticmethod
    def _resolve_deltas(rack_delta: Dict[Tile, int], board_delta: Dict[Pos, Tile]):
        board_hist = {}
        for tile in board_delta.values():
            board_hist.setdefault(tile, 0)
            board_hist += 1

        return board_hist == rack_delta
    

class Dictionary(metaclass=Singleton):
    def __init__(self, path: Path = CSW21_PATH):
        with open(path) as f:
            words = f.read().splitlines()
            self._valid_words = frozenset(words)

    def is_valid(self, word: str):
        return word in self._valid_words