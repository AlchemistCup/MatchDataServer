from typing import Dict
from pathlib import Path
from logging import Logger

from util import Singleton

CSW21_PATH = Path(__file__).resolve().parent / 'CSW21.txt'

n_of_requests = 0
test = 1

class GameStateStore(metaclass=Singleton):
    def __init__(self):
        self._game_state_mapping: Dict[str, GameState] = {}

    def create_new_match(self, match_id, connection_handler):
        assert match_id not in self._game_state_mapping, f"Cannot start new match with match_id={match_id}, this id is already taken"

        self._game_state_mapping[match_id] = GameState(connection_handler)

class GameState():
    def __init__(self, connection_handler) -> None:
        self._connection_handler = connection_handler
        self._bag = TileBag()

class TileBag():
    def __init__(self):
        self._tile_histogram = {
            'A': 9, 'B': 2, 'C': 2, 'D': 4, 'E': 12, 'F': 2, 'G': 3, 'H': 2, 'I': 9,
            'J': 1, 'K': 1, 'L': 4, 'M': 2, 'N': 6, 'O': 8, 'P': 2, 'Q': 1, 'R': 6,
            'S': 4, 'T': 6, 'U': 4, 'V': 2, 'W': 2, 'X': 1, 'Y': 2, 'Z': 1, '?': 2
        }

    def is_feasible(self, rack: str):
        if len(rack) > 7:
            return False
        
        rack_tiles = TileBag._str_to_hist(rack)

        for tile, count in rack_tiles.items():
            if tile not in self._tile_histogram or self._tile_histogram[tile] < count:
                return False
        
        return True
    
    def remove_tiles(self, tiles: str):
        if not self.is_feasible(tiles):
            return False 
        
        for tile in tiles:
            self._tile_histogram[tile] -= 1
        return True
    
    def add_tiles(self, tiles: str):
        for tile in tiles:
            if tile not in self._tile_histogram:
                return False
            self._tile_histogram[tile] += 1
        return True
    
    def get_expected_tiles_on_rack(self) -> int:
        remaining_tiles = sum(self._tile_histogram.values())
        return min(remaining_tiles, 7)

    @staticmethod
    def str_to_hist(tiles: str) -> Dict[str, int]:
        tile_hist = {}
        for tile in tiles:
            tile_hist.setdefault(tile, 0)
            tile_hist[tile] += 1


class RackDeltaResolver():
    def __init__(self, bag: TileBag, logger: Logger) -> None:
        self._deltas = []
        self._remaining_tiles = None
        self._curr_snapshot = None
        self._confidence = 0
        self._bag = bag
        self._expected_tiles = bag.get_expected_tiles_on_rack()
        self._logger = logger

    def add_delta(self, rack):
        if not self._bag.is_feasible(rack):
            self._logger.warning(f'Ignoring rack delta {rack} as it is not feasible given tile bag')
            return False
        
        if self._remaining_tiles is not None:
            if not RackDeltaResolver.is_superset(rack, self._remaining_tiles):
                self._logger.warning(f'Ignoreing rack delta {rack} as it does not contain leftover tiles {self._remaining_tiles}')
                return False

        if rack == self._deltas[-1]:
            self._confidence += 1
            
        self._deltas.append(rack)
    
    @staticmethod
    def is_superset(tiles, remaining):
        tile_hist = TileBag.str_to_hist(tiles)
        for tile, count in TileBag.str_to_hist(remaining):
            if tile not in tile_hist or count > tile_hist[tile]:
                return False
            
        return True

class Dictionary(metaclass=Singleton):
    def __init__(self, path: Path = CSW21_PATH):
        with open(path) as f:
            words = f.read().splitlines()
            self._valid_words = frozenset(words)

    def is_valid(self, word: str):
        return word in self._valid_words