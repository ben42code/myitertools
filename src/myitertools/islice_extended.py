import itertools
from collections import deque
from typing import Iterable, Iterator, TypeVar

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
    rawSlice = slice(*args)

    step = 1 if rawSlice.step is None else rawSlice.step.__int__()

    if step == 0:
        raise ValueError("step argument must not be 0")

    if rawSlice.start is None:
        start = 0 if step > 0 else -1
    else:
        start = rawSlice.start.__index__()

    stop = None if rawSlice.stop is None else rawSlice.stop.__index__()

    sanitizedSlice = slice(start, stop, step)

    # Didn't enable this performance optimization since it would lead to non intuitive behavior when the input is an iterator.
    # It would also be really hard to predict the final state when the input is an iterator (not an iterable).
    # Latest itertools.islice documentation is now explicit on that matter.
    # Behavior consistency is more important than performance in this case.

    # def sameSign(x, y):
    #     return (x >= 0) == (y >= 0)

    # if sanitizedSlice.stop is not None and sameSign(sanitizedSlice.start, sanitizedSlice.stop):
    #     # early stop when we are guaranteed to have no elements to return
    #     # stop index is before start index and step is positive
    #     # ex: (5,2,1), (-2,-5,1)
    #     if sanitizedSlice.step > 0 and sanitizedSlice.stop <= sanitizedSlice.start:
    #         return
    #     # stop index is after start index and step is negative
    #     # ex: (2,5,-1),(-5,-2,-1)
    #     if sanitizedSlice.step < 0 and sanitizedSlice.start <= sanitizedSlice.stop:
    #         return

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
        newDataSource = deque(newDataSource[rawSlice])
        while len(newDataSource) > 0:
            yield newDataSource.popleft()
    else:   # start >= 0, stop is None or >= 0, step > 0
        # Those cases are supported by itertools.islice
        yield from itertools.islice(iterable, *args)
