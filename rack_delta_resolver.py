from enum import Enum
import time
import inspect
from typing import Dict
from logging import Logger

from tile_bag import TileBag
from scrabble import Tile

class RackState(Enum):
    Drawing = 0
    Playing = 1

    def switch(self):
        match self:
            case RackState.Drawing:
                return RackState.Playing
            case RackState.Playing:
                return RackState.Drawing

class RackDeltaResolver():
    MAX_SNAPSHOT_AGE_IN_MS = 3000
    MIN_ACCEPTABLE_CONFIDENCE = 2

    def __init__(self, bag: TileBag, logger: Logger) -> None:
        self._prev_snapshot: Dict[Tile, int] = {}
        self._curr_snapshot: Dict[Tile, int] = {}
        self._state = RackState.Drawing
        self._confidence = 0
        self._last_update = 0
        self._bag = bag
        self._logger = logger

    def process_delta(self, rack: Dict[Tile, int]):        
        match self._state:
            case RackState.Drawing:
                res = self._validate_drawing_delta(rack)
            case RackState.Playing:
                res = self._validate_playing_delta(rack)

        if not res:
            return False
        
        self._last_update = time.time()
        if rack == self._curr_snapshot:
            self._confidence += 1

        self._curr_snapshot = rack
        return True
    
    def end_turn(self):
        if self._state == RackState.Drawing:
            tiles_drawn = RackDeltaResolver._get_delta(self._curr_snapshot, self._prev_snapshot)
            if not self._bag.remove_tiles(tiles_drawn):
                self._logger.error(f"Cannot resolve rack drawing delta resolution, unable to draw {tiles_drawn} from tile bag - should never happen (prev state = {self._prev_snapshot}, curr state = {self._curr_snapshot})")
                return False
            
            expected_n = self._bag.get_expected_tiles_on_rack(self._prev_snapshot) 
            if expected_n != self.n_of_tiles:
                self._logger.error(f"Incorrect # of tiles on rack at the end of drawing turn ({self.n_of_tiles}), expected {expected_n}")
                # Need to throw here to tell top level game state so error can be passed to users
                return False
            
        if (age := (time.time() - self._last_update) * 1000) > RackDeltaResolver.MAX_SNAPSHOT_AGE_IN_MS:
            self._logger.error(f"Most recent update {self._curr_snapshot} received {age:.2f} ms ago is too old to use in end-of-turn resolution")
            return False
        
        if self._confidence < RackDeltaResolver.MIN_ACCEPTABLE_CONFIDENCE:
            self._logger.warning(f"Using snapshot {self._curr_snapshot} with low confidence {self._confidence} in end-of-turn resolution")

        self._state = self._state.switch()
        self._prev_snapshot = self._curr_snapshot
        self._confidence = 0
        return True

    @property
    def current_rack(self):
        return self._curr_snapshot
    
    @property
    def delta(self):
        """
        Returns the difference between the rack's current and previous snapshots
        """
        match self._state:
            case RackState.Playing:
                return RackDeltaResolver._get_delta(self._prev_snapshot, self._curr_snapshot)
            case RackState.Drawing:
                return RackDeltaResolver._get_delta(self._curr_snapshot, self._prev_snapshot)
    
    @property
    def n_of_tiles(self):
        return sum(self._curr_snapshot.values())
    
    @property
    def confidence(self):
        return self.confidence

    def _validate_drawing_delta(self, rack: Dict[Tile, int]):
        assert self._state == RackState.Drawing, f"Called {inspect.stack()[0][3]} in invalid state {self._state}"

        if not RackDeltaResolver._is_superset(rack, self._prev_snapshot):
            self._logger.warning(f'Ignoring rack drawing delta {rack} as it is not a superset of previous rack state {self._prev_snapshot}')
            return False
        
        tiles_drawn = RackDeltaResolver._get_delta(rack, self._prev_snapshot)

        if not self._bag.is_feasible(tiles_drawn):
            self._logger.warning(f'Ignoring rack drawing delta {rack} as tiles drawn {tiles_drawn} are not feasible given tile bag')
            return False
        
        expected_n = self._bag.get_expected_tiles_on_rack(self._prev_snapshot)
        if (sum(self._curr_snapshot.values()) == expected_n
                and sum(rack.values()) != expected_n):
            self._logger.warning(f'Ignoring rack drawing delta {rack} as it does not contain the expected number of tile {expected_n}')
            return False

        return True
    
    def _validate_playing_delta(self, rack: Dict[Tile, int]):
        assert self._state == RackState.Playing, f"Called {inspect.stack()[0][3]} in invalid state {self._state}"

        if not RackDeltaResolver._is_subset(rack, self._prev_snapshot):
            self._logger.warning(f'Ignoring rack playing delta {rack} as it is not a subset of previous rack state {self._prev_snapshot}')
            return False

        return True
    
    @staticmethod
    def _is_superset(current: Dict[Tile, int], previous: Dict[Tile, int]):
        """
        Returns true if current is a superset of previous
        """
        for tile, count in previous.items():
            if tile not in current or count > current[tile]:
                return False
            
        return True
    
    @staticmethod
    def _is_subset(current: Dict[Tile, int], previous: Dict[Tile, int]):
        """
        Returns true if current is a superset of previous
        """
        return RackDeltaResolver._is_superset(previous, current)
    
    @staticmethod
    def _get_delta(superset: Dict[Tile, int], subset: Dict[Tile, int]):
        """
        Returns a histogram of the difference between two histograms, where one is a superset of the other
        """
        assert RackDeltaResolver._is_superset(superset, subset)

        delta = {}
        for tile, count in superset.items():
            if (remaining := count - subset.get(tile, 0)) > 0:
                delta[tile] = remaining

        return delta