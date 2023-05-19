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

enum SensorType {
  board @0;
  rack @1;
}

interface Board {
  assignMatch @0 (matchId :Text) -> (success :Bool);
  confirmMove @1 (move :Move) -> (success :Bool); # Tells board which tiles constituted the last move
  getFullBoardState @2 () -> (boardState :Text); # Used to obtain the full board state when something has gone wrong (i.e. recovering from disconnect). boardState is just a string containing all the tiles data in 
}

interface Rack {
  assignMatch @0 (matchId :Text, player :Player) -> (success :Bool);
}

struct Sensor {
  union {
    board @0 :Board;
    rack @1 :Rack;
  }
}

# Note: when implementing interfaces in python, the argument names must match exactly
interface MatchServer {
  register @0 (macAddr :UInt64, sensorInterface :Sensor) -> (matchId :Text); # If empty string returned this means match hasn't been assigned yet
  pulse @1 (); # Used to keep connection alive while waiting for match to start
  sendMove @2 (matchId :Text, move :Move) -> (success :Bool);
  sendRack @3 (matchId :Text, player :Player, tiles :Text) -> (success :Bool);
}