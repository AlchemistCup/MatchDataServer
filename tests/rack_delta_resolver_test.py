import unittest
import time

from rack_delta_resolver import RackDeltaResolver
from tile_bag import TileBag
from logger import get_logger

logger = get_logger('GameState-ExampleId')

def str_to_dict(rack: str):
    hist = {}
    for letter in rack:
        hist.setdefault(letter, 0)
        hist[letter] += 1
    return hist

class TestProcessDelta(unittest.TestCase):
    # Note: Need to pass copies of rack if rack is mutated later in the test to avoid changing delta in the rack
    def test_valid_draw_delta(self):
        resolver = RackDeltaResolver(TileBag(), logger)

        rack = {}
        self.assertTrue(resolver.process_delta(rack.copy()))

        for letter in ['B', 'D', 'F', 'E', 'E', '?', 'Y']:
            rack.setdefault(letter, 0)
            rack[letter] += 1
            self.assertTrue(resolver.process_delta(rack.copy()))

    def test_reduced_draw_delta_invalid(self):
        resolver = RackDeltaResolver(TileBag(), logger)
        rack = str_to_dict('BDFEE?Y')

        self.assertTrue(resolver.process_delta(rack.copy()))
        for letter in ['B', 'D', 'F', 'E', 'E', '?', 'Y']:
            rack[letter] -= 1
            self.assertFalse(resolver.process_delta(rack.copy()))

    def test_too_long_draw_delta_invalid(self):
        bag = TileBag()
        resolver = RackDeltaResolver(bag, logger)

        too_long_8 = str_to_dict("ABFGEEDP")
        self.assertFalse(resolver.process_delta(too_long_8))

        bag.empty()
        bag.add_tiles({'B': 3})
        too_long_4 = {'B': 4}
        self.assertFalse(resolver.process_delta(too_long_4))

    def test_infeasible_draw_delta_invalid(self):
        resolver = RackDeltaResolver(TileBag(), logger)

        infeasible = {'Z': 2} # Only 1 Z tile in bag
        self.assertFalse(resolver.process_delta(infeasible))

    def test_valid_play_delta(self):
        resolver = RackDeltaResolver(TileBag(), logger)
        rack = str_to_dict("RATES?V")
        self._set_resolver_to_play_mode(resolver, rack)

        self.assertTrue(resolver.process_delta(rack))

        rack = rack.copy() # Use fresh rack
        for letter in rack.keys():
            rack[letter] -= 1
            self.assertTrue(resolver.process_delta(rack.copy()))

        for letter in rack.keys():
            rack[letter] += 1
            self.assertTrue(resolver.process_delta(rack.copy()))

    def test_non_subset_play_delta_invalid(self):
        resolver = RackDeltaResolver(TileBag(), logger)
        rack = str_to_dict("CPLEOBW")
        self._set_resolver_to_play_mode(resolver, rack)

        for rack in ["CPLEOBI", "CPLEV", "?"]:
            rack = str_to_dict(rack)
            self.assertFalse(resolver.process_delta(rack))

    def test_draw_delta_with_leftover_tiles(self):
        resolver = RackDeltaResolver(TileBag(), logger)

        rack = str_to_dict("COWBELP")
        self._set_resolver_to_play_mode(resolver, rack)
        
        rack = str_to_dict("COW")
        self.assertTrue(resolver.process_delta(rack))
        self.assertTrue(resolver.end_turn()) # Back in draw mode with leftover tiles COW

        rack = str_to_dict("COWE")
        self.assertTrue(resolver.process_delta(rack))

        rack = str_to_dict("COER")
        self.assertFalse(resolver.process_delta(rack))
    
    def _set_resolver_to_play_mode(self, resolver: RackDeltaResolver, rack):
        self.assertTrue(resolver.process_delta(rack))
        self.assertTrue(resolver.end_turn())

class TestEndTurn(unittest.TestCase):
    def test_valid_draw_turn(self):
        resolver = RackDeltaResolver(TileBag(), logger)

        rack = str_to_dict("POGBOLP")
        self.assertTrue(resolver.process_delta(rack))
        self.assertTrue(resolver.end_turn())

    def test_valid_play_turn(self):
        resolver = RackDeltaResolver(TileBag(), logger)

        rack = str_to_dict("LSTIUEI")
        self._set_resolver_to_play_mode(resolver, rack)

        rack = str_to_dict("TE")
        self.assertTrue(resolver.process_delta(rack))
        self.assertTrue(resolver.end_turn())

    def test_draw_turn_with_insufficient_tiles_is_invalid(self):
        resolver = RackDeltaResolver(TileBag(), logger)

        rack = str_to_dict("RAES?T")
        self.assertTrue(resolver.process_delta(rack))
        self.assertFalse(resolver.end_turn())

    def test_old_snapshot_is_invalid(self):
        resolver = RackDeltaResolver(TileBag(), logger)
        rack = str_to_dict("RAEES?T")
        self.assertTrue(resolver.process_delta(rack))
        time.sleep(RackDeltaResolver.MAX_SNAPSHOT_AGE_IN_MS / 1000)
        self.assertFalse(resolver.end_turn())

    def _set_resolver_to_play_mode(self, resolver: RackDeltaResolver, rack):
        self.assertTrue(resolver.process_delta(rack))
        self.assertTrue(resolver.end_turn())