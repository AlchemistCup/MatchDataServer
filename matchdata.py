from typing import Dict

n_of_requests = 0

class ConnectionHandler:
    def __init__(self):
        self._available_racks: Dict[int, ] = dict()