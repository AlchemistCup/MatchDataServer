from typing import Dict
from pathlib import Path

from util import Singleton

CSW21_PATH = Path(__file__).resolve().parent / 'CSW21.txt'

n_of_requests = 0
test = 1

class GameStateStore(metaclass=Singleton):
    def __init__(self):
        self._game_state_mapping: Dict[str, GameState]

    def create_new_match(self, match_id, connection_handler):
        assert match_id not in self._game_state_mapping, f"Cannot start new match with match_id={match_id}, this id is already taken"

        self._game_state_mapping[match_id] = GameState(connection_handler)

class GameState():
    def __init__(self, connection_handler) -> None:
        self._connection_handler = connection_handler

class DeltaResolver():
    def __init__(self) -> None:
        self._deltas = []
        self._prev_state = None
        self._confidence = 0

    def add_delta(self, delta):
        if len(self._deltas) != 0:
            if delta == self._deltas[-1]:
                self._confidence += 1
        self._deltas.append(delta)

class Dictionary(metaclass=Singleton):
    def __init__(self, path: Path = CSW21_PATH):
        with open(path) as f:
            words = f.read().splitlines()
            self._valid_words = frozenset(words)

    def is_valid(self, word: str):
        return word in self._valid_words