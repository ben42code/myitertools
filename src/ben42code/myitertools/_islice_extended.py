import itertools
from collections import deque
from typing import Iterable, Iterator, Optional, TypeVar

__all__ = ["islice_extended"]

T = TypeVar('T')


def islice_extended(iterable: Iterable[T], *args) -> Iterator[T]:
    """
    islice_extended(iterable: Iterable[T], *args) -> Iterator[T]
    A custom implementation of slicing for iterables, similar to `itertools.islice`,
    but with additional handling for negative indices and steps.
    Parameters:
        iterable (Iterable[T]): The input iterable to slice.
        *args: Variable-length arguments representing the slice parameters:
            - start (SupportsIndex | None): The starting index of the slice. Can be negative.
              If None, defaults to 0 (first element) if step is positive, or -1 (last element) if step is negative.
            - stop (SupportsIndex | None): The stopping index of the slice. Can be negative.
              If None, the slice continues to the end of the iterable.
            - step (SupportsInt | None): The step size for the slice. Can be negative.
              If None or not provided; defaults to 1. Must not be 0.
    Returns:
        Iterator[T]: An iterator over the sliced elements of the input iterable.
    Raises:
        ValueError: If the step size is 0.
    Notes:
        If the input is an iterator, then fully consuming the islice advances the input iterator
            - by max(start, stop) if start and stop and step are positive. (itertools.islice behavior)
            - by start+1 if if start and stop are positive and step is negative.
            - until StopIteration is raised if start or stop are negative.
    """
    rawSlice: slice = slice(*args)

    step: int = 1 if rawSlice.step is None else int(rawSlice.step)

    if step == 0:
        raise ValueError("step argument must not be 0")

    if rawSlice.start is None:
        start: int = 0 if step > 0 else -1
    else:
        start: int = rawSlice.start.__index__()

    stop: Optional[int] = None if rawSlice.stop is None else rawSlice.stop.__index__()

    sanitizedSlice: slice = slice(start, stop, step)

    if sanitizedSlice.start < 0 or (sanitizedSlice.stop is not None and sanitizedSlice.stop < 0):
        # we need to retrieve the whole content
        # negative indexes are relative to the end of the stream
        newDataSource = list(iterable)
    elif sanitizedSlice.step < 0:
        # negative step means we only need all the data up to the start element included
        # since start index can exceed that iterable size, we can't be too smart...hence this brute force approach
        newDataSource = list(itertools.islice(iterable, sanitizedSlice.start + 1))
    else:
        newDataSource = None

    if newDataSource is not None:
        # only keep that the elements that will be returned
        # and store them in a deque to be able to release them asap
        newDataSource = deque(newDataSource[rawSlice])
        while len(newDataSource) > 0:
            yield newDataSource.popleft()
    else:   # start >= 0, stop is None or >= 0, step > 0
        # Those cases are supported by itertools.islice
        yield from itertools.islice(iterable, *args)
