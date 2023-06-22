import time
from typing import Dict
from logging import Logger

from scrabble.src.board_pos import Pos
from scrabble.src.board import Board
from scrabble.src.tile import Tile
from scrabble.src.move import Move

class BoardDeltaResolver():
    # Currently identical to values in RackDeltaResolver, but separate values are used to facilitate individual tuning in the future
    MAX_SNAPSHOT_AGE_IN_MS = 2000
    MIN_ACCEPTABLE_CONFIDENCE = 2

    def __init__(self, board: Board, logger: Logger) -> None:
        self._board = board
        self._delta: Dict[Pos, Tile] = {}
        self._confidence = 0
        self._last_update = 0
        self._logger = logger

    def process_delta(self, delta: Dict[Pos, Tile]):
        if not self._validate_delta(delta):
            return False
        
        self._last_update = time.time()
        if delta == self._delta:
            self._confidence += 1

        self._delta = delta
        return True

    def end_turn(self):
        move = BoardDeltaResolver._delta_to_move(self._delta)
        if not move.is_valid:
            self._logger.error(f"Cannot use move formed by delta {move} in end-of-turn resolution as it is invalid (should never happen)")
            return False
            
        if age := (time.time() - self._last_update) * 1000 > BoardDeltaResolver.MAX_SNAPSHOT_AGE_IN_MS:
            self._logger.error(f"Most recent update {self._curr_snapshot} received {age:.2f} ms ago is too old to use in end-of-turn resolution")
            return False
        
        if self._confidence < BoardDeltaResolver.MIN_ACCEPTABLE_CONFIDENCE:
            self._logger.warning(f"Using delta {self._delta} with low confidence {self._confidence} for end-of-turn resolution")

        if not self._board.apply_move(move):
            self._logger.error(f"Unable to apply move formed by delta {move} to board state")
            return False

        self._delta = {}
        self._confidence = 0
        return True

    def _validate_delta(self, delta: Dict[Pos, Tile]):
        confirmed_positions = []

        for pos, tile in delta.items():
            if placed_tile := self._board.get_tile(pos) is not None: 
                if tile != placed_tile:
                    self._logger.warning(f'Ignoring board delta {delta} because measured {tile} does not match confirmed {placed_tile} @ {pos}')
                    return False
                else:
                    confirmed_positions.append(pos)

        for pos in confirmed_positions:
            del delta[pos]
        
        if len(delta) > 7:
            self._logger.warning(f'Ignoring board delta {delta} as it contains more than 7 tiles (should be impossible)')
            return False

        move = BoardDeltaResolver._delta_to_move(delta)
        return move.is_valid
    
    @staticmethod
    def _delta_to_move(delta: Dict[Pos, Tile]):
        return Move(list(delta.values()), list(delta.keys()))