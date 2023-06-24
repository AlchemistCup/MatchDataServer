import unittest
import time

from scrabble import Tile
from rack_delta_resolver import RackDeltaResolver
from tile_bag import TileBag
from logger import get_logger

logger = get_logger('GameState-ExampleId')

def to_rack(rack: str):
    hist = {}
    for letter in rack:
        tile = Tile(letter)
        hist.setdefault(tile, 0)
        hist[tile] += 1
    return hist

class TestProcessDelta(unittest.TestCase):
    # Note: Need to pass copies of rack if rack is mutated later in the test to avoid changing delta in the rack
    def test_valid_draw_delta(self):
        resolver = RackDeltaResolver(TileBag(), logger)

        rack = {}
        self.assertTrue(resolver.process_delta(rack.copy()))

        for letter in ['B', 'D', 'F', 'E', 'E', '?', 'Y']:
            tile = Tile(letter)
            rack.setdefault(tile, 0)
            rack[tile] += 1
            self.assertTrue(resolver.process_delta(rack.copy()))

    def test_reduced_draw_delta_invalid(self):
        resolver = RackDeltaResolver(TileBag(), logger)
        rack = to_rack('BDFEE?Y')

        self.assertTrue(resolver.process_delta(rack.copy()))
        for letter in ['B', 'D', 'F', 'E', 'E', '?', 'Y']:
            tile = Tile(letter)
            rack[tile] -= 1
            self.assertFalse(resolver.process_delta(rack.copy()))

    def test_too_long_draw_delta_valid(self):
        # This can happen if a player accidentally draws too many tiles. System needs to detect and warn users if this happens
        bag = TileBag()
        resolver = RackDeltaResolver(bag, logger)

        too_long_8 = to_rack("ABFGEEDP")
        self.assertTrue(resolver.process_delta(too_long_8))

    def test_infeasible_draw_delta_invalid(self):
        resolver = RackDeltaResolver(TileBag(), logger)

        infeasible = {Tile('Z'): 2} # Only 1 Z tile in bag
        self.assertFalse(resolver.process_delta(infeasible))

    def test_valid_play_delta(self):
        resolver = RackDeltaResolver(TileBag(), logger)
        rack = to_rack("RATES?V")
        self._set_resolver_to_play_mode(resolver, rack)

        self.assertTrue(resolver.process_delta(rack))

        rack = rack.copy() # Use fresh rack
        for tile in rack.keys():
            rack[tile] -= 1
            self.assertTrue(resolver.process_delta(rack.copy()))

        for tile in rack.keys():
            rack[tile] += 1
            self.assertTrue(resolver.process_delta(rack.copy()))

    def test_non_subset_play_delta_invalid(self):
        resolver = RackDeltaResolver(TileBag(), logger)
        rack = to_rack("CPLEOBW")
        self._set_resolver_to_play_mode(resolver, rack)

        for rack in ["CPLEOBI", "CPLEV", "?"]:
            rack = to_rack(rack)
            self.assertFalse(resolver.process_delta(rack))

    def test_draw_delta_with_leftover_tiles(self):
        resolver = RackDeltaResolver(TileBag(), logger)

        rack = to_rack("COWBELP")
        self._set_resolver_to_play_mode(resolver, rack)
        
        rack = to_rack("COW")
        self.assertTrue(resolver.process_delta(rack))
        self.assertTrue(resolver.end_turn()) # Back in draw mode with leftover tiles COW

        rack = to_rack("COWE")
        self.assertTrue(resolver.process_delta(rack))

        rack = to_rack("COER")
        self.assertFalse(resolver.process_delta(rack))
    
    def _set_resolver_to_play_mode(self, resolver: RackDeltaResolver, rack):
        self.assertTrue(resolver.process_delta(rack))
        self.assertTrue(resolver.end_turn())

class TestEndTurn(unittest.TestCase):
    def test_valid_draw_turn(self):
        resolver = RackDeltaResolver(TileBag(), logger)

        rack = to_rack("POGBOLP")
        self.assertTrue(resolver.process_delta(rack))
        self.assertTrue(resolver.end_turn())

    def test_valid_play_turn(self):
        resolver = RackDeltaResolver(TileBag(), logger)

        rack = to_rack("LSTIUEI")
        self._set_resolver_to_play_mode(resolver, rack)

        rack = to_rack("TE")
        self.assertTrue(resolver.process_delta(rack))
        self.assertTrue(resolver.end_turn())

    def test_draw_turn_with_too_few_tiles_is_invalid(self):
        resolver = RackDeltaResolver(TileBag(), logger)

        rack = to_rack("RAES?T")
        self.assertTrue(resolver.process_delta(rack))
        self.assertFalse(resolver.end_turn())

    def test_draw_turn_with_too_many_tiles_is_invalid(self):
        resolver = RackDeltaResolver(TileBag(), logger)

        rack = to_rack("BIBIMPAP")
        self.assertTrue(resolver.process_delta(rack))
        self.assertFalse(resolver.end_turn())

    def test_old_snapshot_is_invalid(self):
        resolver = RackDeltaResolver(TileBag(), logger)
        rack = to_rack("RAEES?T")
        self.assertTrue(resolver.process_delta(rack))
        time.sleep(RackDeltaResolver.MAX_SNAPSHOT_AGE_IN_MS / 1000)
        self.assertFalse(resolver.end_turn())

    def _set_resolver_to_play_mode(self, resolver: RackDeltaResolver, rack):
        self.assertTrue(resolver.process_delta(rack))
        self.assertTrue(resolver.end_turn())