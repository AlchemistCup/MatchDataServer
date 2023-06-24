from enum import Enum
from pathlib import Path
import random
import string
from typing import Dict, Tuple, Optional

from util import Singleton, Result
from logger import get_logger

from tile_bag import TileBag
from rack_delta_resolver import RackDeltaResolver, RackState
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
    _VALID_MATCH_ID_CHARACTERS = string.ascii_letters + string.digits
    def __init__(self):
        self._game_state_mapping: Dict[str, GameState] = {}

    def generate_new_match_id(self):
        def create_random_id():
            return ''.join(random.choices(GameStateStore._VALID_MATCH_ID_CHARACTERS, k=8))

        while (match_id := create_random_id()) in self._game_state_mapping:
            match_id = create_random_id()
        
        return match_id


    def create_new_match(self, match_id: str, player_names: Tuple[str, str], connection_handler):
        assert match_id not in self._game_state_mapping, f"Cannot start new match with match_id={match_id}, this id is already taken"

        self._game_state_mapping[match_id] = GameState(match_id, player_names, connection_handler)

    def get_game_state(self, match_id):
        return self._game_state_mapping.get(match_id)
    

class EndOfTurn():
    def __init__(self, score: int, n_of_blanks: int, end_of_game_bonus: Optional[int]) -> None:
        self.score = score
        self.n_of_blanks = n_of_blanks
        self.end_of_game_bonus = end_of_game_bonus

    def to_dict(self):
        res = {
            'score': self.score,
            'blanks': self.n_of_blanks
        }

        if self.end_of_game_bonus:
            res['end_game_bonus'] = self.end_of_game_bonus

        return res

class PlayerInfo():
    def __init__(self, name: str) -> None:
        self.name = name
        self.score = 0
        self.time = 0

class GameState():
    def __init__(self, match_id: str, player_names: Tuple[str, str], connection_handler) -> None:
        self._match_id = match_id
        self._connection_handler = connection_handler
        self._bag = TileBag()
        self._board = Board()
        base_logger_name = f'{__class__.__name__}-{match_id}'
        self._logger = get_logger(base_logger_name)
        self._delta_resolvers = {
            SensorRole.board: BoardDeltaResolver(self._board, get_logger(f'{base_logger_name}-board')),
            SensorRole.player1: RackDeltaResolver(self._bag, get_logger(f'{base_logger_name}-rackP1')),
            SensorRole.player2: RackDeltaResolver(self._bag, get_logger(f'{base_logger_name}-rackP2'))
        }    
        p1_name, p2_name = player_names
        self._player_info = {
            SensorRole.player1: PlayerInfo(p1_name),
            SensorRole.player2: PlayerInfo(p2_name)
        }
        self._turn_n = 0

    @property
    def turn_number(self):
        return self._turn_n

    def process_delta(self, role: SensorRole, delta):
        self._logger.debug2(f'Received delta {delta} from sensor {role}')
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

        self._logger.debug2(f"Finished processing delta {delta} from role {role}")
        return res
    
    async def end_turn(self, player_time) -> Result[EndOfTurn]:
        """
        Returns the associated data related to the end of a turn, or an error message, wrapped in a result type
        """
        if self._get_playing_rack().state != RackState.Playing:
            self._logger.error(f"{self._get_playing_player()}'s rack resolver not in play state. Should only happen if player 1 does not draw 7 tiles before playing.")
            return Result.failure("Game State error")
        
        drawing_rack_resolver = self._get_drawing_rack()
        # Currently, this partially duplicates the end_turn logic in RackDeltaResolver, which is why this check needs to be done first. Potentially could be nicer to warn players of this before the end of the turn.
        if drawing_rack_resolver.n_of_tiles > 7:
            drawing_player = self._get_playing_player().opposite
            self._logger.error(f"{drawing_player} drew too many tiles ({drawing_rack_resolver.n_of_tiles}). Rack state = {drawing_rack_resolver.current_rack}")
            return Result.failure(f"{drawing_player} drew too many tiles ({drawing_rack_resolver.n_of_tiles})")

        playing_rack = self._get_playing_rack()
        playing_rack_delta = playing_rack.delta
        board_delta = self._board_resolver.delta

        if any(not resolver.end_turn() for resolver in self._delta_resolvers.values()):
            self._logger.error("Unable to resolve end of turn deltas due to resolver error")
            return Result.failure("Game State error")
        
        n_of_tiles_from_rack = sum(count for count in playing_rack_delta.values())
        n_of_tiles_played = len(board_delta)
        move = None
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
            return Result.failure("Game State error")
        
        end_of_turn_info = EndOfTurn(0, 0)
        if move is not None:
            bonus = None
            if self._bag.n_of_tiles == 0 and playing_rack.n_of_tiles == 0:
                remaining_tiles = drawing_rack_resolver.current_rack
                bonus = 2 * sum(tile.value * count for tile, count in remaining_tiles.items())
                self._logger.info(f"{self._get_playing_player()} has finished the game, received {bonus} point bonus")

            end_of_turn_info = EndOfTurn(
                score=self._board.get_score(),
                n_of_blanks=move.n_of_unset_blanks,
                end_of_game_bonus=bonus
            )

        self._player_info[self._get_playing_player()].time = player_time
        self._turn_n += 1        
        self._logger.info(f"Board State:\n{self._board}")
        self._logger.info(f"P1 Rack State: {self._delta_resolvers[SensorRole.player1].current_rack}")
        self._logger.info(f"P2 Rack State: {self._delta_resolvers[SensorRole.player2].current_rack}")
        # TODO: Send rack info to woogles

        return Result.success(end_of_turn_info)
    
    @property
    def board(self):
        return self._board

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