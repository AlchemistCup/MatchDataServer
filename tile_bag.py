from typing import Dict

from scrabble import Tile
class TileBag():
    STARTING_BAG = {
        'A': 9, 'B': 2, 'C': 2, 'D': 4, 'E': 12, 'F': 2, 'G': 3, 'H': 2, 'I': 9,
        'J': 1, 'K': 1, 'L': 4, 'M': 2, 'N': 6, 'O': 8, 'P': 2, 'Q': 1, 'R': 6,
        'S': 4, 'T': 6, 'U': 4, 'V': 2, 'W': 2, 'X': 1, 'Y': 2, 'Z': 1, '?': 2
    }

    def __init__(self):
        self._tile_histogram = {Tile(letter): count for letter, count in self.STARTING_BAG.items()}

    def is_feasible(self, rack: Dict[Tile, int]):        
        for tile, count in rack.items():
            if self._tile_histogram[tile] < count:
                return False
        
        return True
    
    def remove_tiles(self, tiles: Dict[Tile, int]):
        if not self.is_feasible(tiles):
            return False 
        
        for tile, count in tiles.items():
            self._tile_histogram[tile] -= count
        return True
    
    def add_tiles(self, tiles: Dict[Tile, int]):
        for tile, count in tiles.items():
            self._tile_histogram[tile] += count
        return True
    
    def empty(self):
        """
        Completely empties the tile bag. Used to facilitate unit testing
        """
        for tile in self._tile_histogram.keys():
            self._tile_histogram[tile] = 0
    
    def get_expected_tiles_on_rack(self, rack: Dict[Tile, int]) -> int:
        tiles_on_rack = sum(rack.values())
        tiles_in_bag = sum(self._tile_histogram.values())
        return min(tiles_on_rack + tiles_in_bag, 7)
    
    @property
    def n_of_tiles(self):
        """
        Returns the number of tiles left in the bag
        """
        return sum(self._tile_histogram.values())