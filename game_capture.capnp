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

# Note: when implementing interfaces in python, the argument names must match exactly
interface Board {
  assignMatch @0 (dataFeed :BoardFeed) -> (success :Bool);
  confirmMove @1 (move :Move) -> (success :Bool); # Tells board which tiles constituted the last move
  getFullBoardState @2 () -> (boardState :Text); # Used to obtain the full board state when something has gone wrong (i.e. recovering from disconnect). boardState is just a string containing all the tiles data in array order (row major)
}

interface Rack {
  assignMatch @0 (dataFeed :RackFeed) -> (success :Bool);
}

struct Sensor {
  union {
    board @0 :Board;
    rack @1 :Rack;
  }
}

# Used to publish rack information to the server
interface RackFeed {
  sendRack @0 (matchId :Text, player :Player, tiles :Text) -> (success :Bool);
}

# Used to publish board information to the server
interface BoardFeed {
  sendMove @0 (matchId :Text, move :Move) -> (success :Bool);
}

# Generic server interface used to handle logic common to both sensors
interface MatchServer {
  register @0 (macAddr :UInt64, sensorInterface :Sensor) -> (dataFeed :DataFeed); # If dataFeed is none then sensor has not yet been allocated to a match
  pulse @1 (); # Used to keep connection alive while waiting for match to start

  struct DataFeed {
    union {
      board @0 :BoardFeed;
      rack @1 :RackFeed;
      none @2 :Void;
    }
  }
}