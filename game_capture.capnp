@0x970ab67bbcf9e1cb;

struct Move {
  tiles @0 :List(Tile);

  struct Tile {
    value @0 :Int8;
    pos @1 :Pos;

    struct Pos {
      row @0 :UInt8;
      col @1 :UInt8;
    }
  }
}

enum Player {
	player1 @0;
	player2 @1;
}

struct Rack {
  player @0 :Player;
  tiles @1 :Text;
}

# Note: when implementing interfaces in python, the argument names must match exactly
interface MatchServer {
  pulse @0 (macAddr :UInt64) -> (matchId :Text); # If empty string returned this means match hasn't been assigned yet
  sendMove @1 (matchId :Text, move :Move) -> (success :Bool);
  sendRack @2 (matchId :Text, rack :Rack) -> (success :Bool);
}

interface BoardFeed {
  confirmMove @0 (move :Move) -> (success :Bool); # Tells board which tiles constituted the last move
  getFullBoardState @1 () -> (boardState :Text); # Used to obtain the full board state when something has gone wrong (i.e. recovering from disconnect). boardState is just a string containing all the tiles data in 
}
