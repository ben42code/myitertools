from typing import Iterable, Iterator, TypeVar

__all__ = ["IteratorCounter"]

T = TypeVar('T')


class IteratorCounter(Iterator[T]):
    """
    An iterator/iterable wrapper that counts the number of items iterated.
    """
    def __init__(self, iterator: Iterator[T] | Iterable[T]):
        self._iterator = iter(iterator)
        self.count = 0

    def __iter__(self) -> 'IteratorCounter[T]':
        return self

    def __next__(self) -> T:
        value = next(self._iterator)
        self.count += 1
        return value
