import unittest
from typing import Dict

from scrabble import Tile
from tile_bag import TileBag

def to_rack(letter_hist: Dict[str, int]):
    return {Tile(letter): count for letter, count in letter_hist.items()}

class TestIsFeasible(unittest.TestCase):
    def test_valid_full_bag(self):
        bag = TileBag()
        rack = to_rack({
            'B': 1,
            'I': 1,
            'N': 2,
            'E': 1,
            'R': 1,
            'S': 1 
        })
        self.assertTrue(bag.is_feasible(rack))

    def test_too_many_tiles_valid(self):
        bag = TileBag()
        rack = to_rack({
            'C': 1,
            'J': 1,
            'O': 2,
            'F': 1,
            'A': 1,
            'W': 1,
            'Z': 1
        })
        self.assertTrue(bag.is_feasible(rack))

    def test_invalid_no_letter_left(self):
        bag = TileBag()
        rack = to_rack({
            '?': 1, # Only 1 ? left in bag
            'L': 1,
            'U': 1,
            'Q': 1, # No Q left in bag
            'A': 1,
            'M': 2 # No Ms left in bag
        })
        self.assertTrue(bag.remove_tiles(rack))

        invalid_q = to_rack({
            'Q': 1,
            'B': 2,
            'N': 2,
            'E': 2
        })

        invalid_m = to_rack({
            'M': 1,
            'O': 3
        })

        invalid_blank = to_rack({
            '?': 2,
            'E': 1
        })

        for invalid in [invalid_q, invalid_m, invalid_blank]:
            self.assertFalse(bag.is_feasible(invalid))

class TestExpectedTiles(unittest.TestCase):
    def test_7_tiles(self):
        bag = TileBag()
        self.assertEqual(bag.get_expected_tiles_on_rack({}), 7)

        rack = to_rack({
            'A': 1,
            'I': 1,
            'N': 1,
            'M': 1,
            'K': 1,
            'E': 2 
        })
        self.assertTrue(bag.remove_tiles(rack))
        self.assertEqual(bag.get_expected_tiles_on_rack({}), 7)

    def test_few_tiles(self):
        bag = TileBag()

        # Easy way to empty bag
        bag.empty()

        self.assertEqual(bag.get_expected_tiles_on_rack({}), 0)
        self.assertEqual(bag.get_expected_tiles_on_rack(to_rack({'A': 1, 'E': 6})), 7)

        bag.add_tiles(to_rack({
            'T': 1,
            'S': 1,
            'G': 1
        }))

        self.assertEqual(bag.get_expected_tiles_on_rack({}), 3)
        self.assertEqual(bag.get_expected_tiles_on_rack(to_rack({'G': 2})), 5)