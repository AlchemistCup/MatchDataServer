from enum import Enum
from pathlib import Path
from typing import Dict, Tuple, List

from util import Singleton
from tcp_server import SensorRole
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
        self._connection_handler = connection_handler
        self._bag = TileBag()
        self._board = Board()
        self._logger = get_logger(f'{__class__.__name__}-{match_id}')
        self._delta_resolvers = {
            SensorRole.board: BoardDeltaResolver(self._board, self._logger),
            SensorRole.player1: RackDeltaResolver(self._bag, self._logger),
            SensorRole.player2: RackDeltaResolver(self._bag, self._logger)
        }

    def get_resolver(self, role: SensorRole):
        return self._delta_resolvers.get(role)                

class Dictionary(metaclass=Singleton):
    def __init__(self, path: Path = CSW21_PATH):
        with open(path) as f:
            words = f.read().splitlines()
            self._valid_words = frozenset(words)

    def is_valid(self, word: str):
        return word in self._valid_words