import unittest
from typing import Dict
import time

from board_delta_resolver import BoardDeltaResolver
from scrabble import Board, Pos, Tile
from logger import get_logger

logger = get_logger('GameState-ExampleId')

class TestProcessDelta(unittest.TestCase):
    def test_valid_delta_empty_board(self):
        resolver = BoardDeltaResolver(Board(), logger)

        delta = {
            Pos(0, 0): Tile('a'),
            Pos(0, 1): Tile('g'),
            Pos(0, 2): Tile('e')
        }
        self.assertTrue(resolver.process_delta(delta))

    def test_too_long_delta_invalid(self):
        resolver = BoardDeltaResolver(Board(), logger)

        delta = {
            Pos(0, 0): Tile('a'),
            Pos(0, 1): Tile('g'),
            Pos(0, 2): Tile('r'),
            Pos(0, 3): Tile('i'),
            Pos(0, 4): Tile('c'),
            Pos(0, 5): Tile('u'),
            Pos(0, 6): Tile('l'),
            Pos(0, 7): Tile('t')
        }
        self.assertFalse(resolver.process_delta(delta))

    def test_invalid_move_delta_invalid(self):
        resolver = BoardDeltaResolver(Board(), logger)

        delta = {
            Pos(4, 12): Tile('c'),
            Pos(5, 12): Tile('u'),
            Pos(6, 12): Tile('l'),
            Pos(7, 13): Tile('t')
        }
        self.assertFalse(resolver.process_delta(delta))

    def test_delta_with_confirmed_info_valid(self):
        resolver = BoardDeltaResolver(Board(), logger)

        delta = {
            Pos(7, 3): Tile('q'),
            Pos(7, 4): Tile('u'),
            Pos(7, 5): Tile('a'),
            Pos(7, 6): Tile('l'),
            Pos(7, 7): Tile('i'),
            Pos(7, 8): Tile('f'),
            Pos(7, 9): Tile('y'),
        }

        self._apply_move_to_resolver(resolver, delta)

        delta = {
            Pos(7, 3): Tile('q'),
            Pos(7, 6): Tile('l'),
            Pos(7, 7): Tile('i'),
            Pos(7, 8): Tile('f'),
            Pos(7, 9): Tile('y'),

            Pos(6, 7): Tile('d'),
            Pos(8, 7): Tile('v'),
            Pos(9, 7): Tile('a'),
            Pos(10, 7): Tile('n'),
        }

        self._apply_move_to_resolver(resolver, delta)

    def test_delta_with_conflicting_info_is_invalid(self):
        resolver = BoardDeltaResolver(Board(), logger)

        delta = {
            Pos(7, 7): Tile('s'),
            Pos(8, 7): Tile('e'),
            Pos(9, 7): Tile('n'),
            Pos(10, 7): Tile('a'),
            Pos(11, 7): Tile('r'),
            Pos(12, 7): Tile('i'),
            Pos(13, 7): Tile('i'),
        }

        self._apply_move_to_resolver(resolver, delta)

        delta = {
            Pos(7, 7): Tile('e'),
            Pos(7, 8): Tile('a'),
            Pos(7, 9): Tile('u'),
            Pos(7, 10): Tile('x'),
        }
        self.assertFalse(resolver.process_delta(delta))

    def test_delta_over_undone_move_is_valid(self):
        board = Board()
        resolver = BoardDeltaResolver(board, logger)

        delta = {
            Pos(7, 7): Tile('q'),
            Pos(7, 8): Tile('u'),
            Pos(7, 9): Tile('a'),
        }

        self._apply_move_to_resolver(resolver, delta)
        board.undo_move() # Move undone by challenge
        delta = {
            Pos(7, 7): Tile('a'),
            Pos(7, 8): Tile('c'),
            Pos(7, 9): Tile('t'),
        }

        self.assertTrue(resolver.process_delta(delta))

    def _apply_move_to_resolver(self, resolver: BoardDeltaResolver, delta: Dict[Pos, Tile]):
        for i in range(len(delta) + 1):
            d = dict(list(delta.items())[:i])
            self.assertTrue(resolver.process_delta(d))

        self.assertTrue(resolver.process_delta(delta))
        self.assertTrue(resolver.end_turn())

class TestEndTurn(unittest.TestCase):
    def test_empty_delta_valid(self):
        resolver = BoardDeltaResolver(Board(), logger)
        self._apply_move_to_resolver(resolver, {})

    def test_unappliable_move_invalid(self):
        resolver = BoardDeltaResolver(Board(), logger)

        delta = {
            Pos(7, 7): Tile('a'),
            Pos(7, 10): Tile('c'),
            Pos(7, 9): Tile('t'),
        }

        self.assertTrue(resolver.process_delta(delta))
        self.assertFalse(resolver.end_turn())

    def test_old_delta_invalid(self):
        resolver = BoardDeltaResolver(Board(), logger)

        delta = {
            Pos(7, 3): Tile('j'),
            Pos(7, 4): Tile('u'),
            Pos(7, 5): Tile('m'),
            Pos(7, 6): Tile('a'),
            Pos(7, 7): Tile('r'),
            Pos(7, 8): Tile('t'),
        }

        self.assertTrue(resolver.process_delta(delta))
        time.sleep(BoardDeltaResolver.MAX_SNAPSHOT_AGE_IN_MS / 1000)
        self.assertFalse(resolver.end_turn())

    def _apply_move_to_resolver(self, resolver: BoardDeltaResolver, delta: Dict[Pos, Tile]):
        for i in range(len(delta) + 1):
            d = dict(list(delta.items())[:i])
            self.assertTrue(resolver.process_delta(d))

        self.assertTrue(resolver.process_delta(delta))
        self.assertTrue(resolver.end_turn())