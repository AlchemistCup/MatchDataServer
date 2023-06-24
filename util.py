from typing import Optional, TypeVar, Generic

class Singleton(type):
    _instances = {}
    def __call__(cls, *args, **kwargs):
        if cls not in cls._instances:
            cls._instances[cls] = super(Singleton, cls).__call__(*args, **kwargs)
        return cls._instances[cls]
    
T = TypeVar('T')
class Result(Generic[T]):
    """
    Represents an F# Result type
    """
    def __init__(self, value: Optional[T] = None, error: Optional[str] = None):
        self.value = value
        self.error = error
        self.is_success = error is None

    @staticmethod
    def success(value: T) -> 'Result[T]':
        return Result(value=value)

    @staticmethod
    def failure(error: str) -> 'Result[T]':
        return Result(error=error)