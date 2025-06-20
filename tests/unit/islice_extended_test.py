from __future__ import annotations

import gc
import itertools
import platform
import unittest
import weakref
from collections import deque
from contextlib import nullcontext
from typing import Iterable, Iterator, NamedTuple
from unittest.mock import Mock

from ben42code.myitertools import islice_extended


def build_IteratorMock(side_effect) -> Mock:
    IteratorMock = Mock()
    IteratorMock.__iter__ = Mock(return_value=IteratorMock)
    IteratorMock.__next__ = Mock(side_effect=side_effect)

    return IteratorMock


def normalizeSlice(iterableSize, start, stop, step):
    if step is None:
        step = 1

    if start is None:
        start = 0 if step > 0 else -1

    if stop is None:
        stop = max(iterableSize + 1, start + 1)
        if step < 0:
            stop = -stop
    return start, stop, step


class IteratorWithWeakReferences:
    """
    A class that wraps an iterator and provides weak references to its elements.
    This class allows iteration over a collection of objects while maintaining
    weak references to the original objects. It can be used to track the validity
    of the objects (i.e., whether they are still alive or has been deleted).
    """
    class _AnObj:
        pass

    @classmethod
    def FROM_SIZE(cls, size: int) -> IteratorWithWeakReferences:
        return cls([IteratorWithWeakReferences._AnObj() for _ in range(size)])

    def __init__(self, iterable: Iterable):
        self._data = deque(element for element in iterable)
        self._weakReferences = [weakref.ref(a) for a in self._data]

    def __iter__(self) -> Iterator:
        return self

    def __next__(self) -> object:
        if len(self._data) == 0:
            raise StopIteration
        return self._data.popleft()

    def weakReferencesState(self) -> list[bool]:
        # CPython does reference counting.
        # GC is not required when ref counting is supported.
        platform.python_implementation() == 'CPython' or gc.collect()
        return [wr() is not None for wr in self._weakReferences]


def expectedIterationsForNElements(iterableSize, start, stop, step, numberOfElements: int | None = None) -> int:
    """
    This function is used to determine the expected number of iterations after some elements have been consumed.
    It is used to test the behavior of the islice_extended function when it is called with a specific set of parameters.
    """
    if numberOfElements == 0:
        return 0

    stopWasNotNone = stop is not None
    start, stop, step = normalizeSlice(iterableSize, start, stop, step)

    if start < 0 or stop < 0 and stopWasNotNone:
        expectedCallCount = iterableSize + 1
    elif step < 0:
        expectedCallCount = min(start + 1, iterableSize + 1)
    elif start >= 0 and stop >= 0 and step > 0:
        iteratorMockRegularIslice = build_IteratorMock(range(iterableSize))
        iterator_islice = itertools.islice(iteratorMockRegularIslice, start, stop, step)
        while numberOfElements is None or numberOfElements > 0:
            try:
                next(iterator_islice)
                if numberOfElements is not None:
                    numberOfElements -= 1
            except StopIteration:
                break
        expectedCallCount = iteratorMockRegularIslice.__next__.call_count

    return expectedCallCount


class Islice_extended_Test(unittest.TestCase):

    def test_withStop_expectedValues(self):
        for index, (iterable, stop) in enumerate(itertools.product(
            [range(0), range(10)],                              # iterable
            [None, -15, -10, -9, -4, -1, 0, 1, 4, 9, 10, 15],   # stop
        )):
            # remove nullcontext() for more details...but pay a dear execution time price in VSCode
            with nullcontext() or self.subTest(f"index:{index:02d} iterable:{iterable} stop:{stop}"):

                # arrange/act
                iteratorFromSlice = islice_extended(iterable, stop)

                # assert
                self.assertEqual(list(iteratorFromSlice), list(iterable)[:stop])

    def test_withStartStop_expectedValues(self):
        for index, (iterable, start, stop) in enumerate(itertools.product(
            [range(0), range(10)],                              # iterable
            [None, -15, -10, -9, -4, -1, 0, 1, 4, 9, 10, 15],   # start
            [None, -15, -10, -9, -4, -1, 0, 1, 4, 9, 10, 15],   # stop
        )):
            # remove nullcontext() for more details...but pay a dear execution time price in VSCode
            with nullcontext() or self.subTest(f"index:{index:04d} iterable:{iterable} start:{start} stop:{stop}"):

                # arrange/act
                iteratorFromSlice = islice_extended(iterable, start, stop)

                # assert
                self.assertEqual(list(iteratorFromSlice), list(iterable)[start:stop])

    def test_withStartStopStep_expectedValues(self):
        for index, (iterable, start, stop, step) in enumerate(itertools.product(
            [range(0), range(10)],                              # iterable
            [None, -15, -10, -9, -4, -1, 0, 1, 4, 9, 10, 15],   # start
            [None, -15, -10, -9, -4, -1, 0, 1, 4, 9, 10, 15],   # stop
            [None, -7, -3, -1, 1, 3, 7],                        # step
        )):
            # remove nullcontext() for more details...but pay a dear execution time price in VSCode
            with nullcontext() or self.subTest(f"index:{index:04d} iterable:{iterable} start:{start} stop:{stop} step:{step}"):

                # arrange/act
                iteratorFromSlice = islice_extended(iterable, start, stop, step)

                # assert
                self.assertEqual(list(iteratorFromSlice), list(iterable)[start:stop:step])

    def test_withZeroStep_assertWhenIterated(self):
        # arrange
        slicedIterator = islice_extended(range(10), 0, 3, 0)

        # assert
        with self.assertRaises(ValueError):
            # act
            next(slicedIterator)

    def test_withZeroStep_noAssertWhenNotIterated(self):
        # arrange/act/assert
        islice_extended(range(10), 0, 3, 0)

    def test_atEndOfStream_alwaysRaiseStopIteration(self):

        # arrange
        slicedIterator = islice_extended(range(10), None)
        list(slicedIterator)    # consume the whole iterator

        # doing it twice, because...why not😁
        for _ in range(2):
            # assert
            with self.assertRaises(StopIteration):
                # act
                next(slicedIterator)

    def test_atEndOfStream_neverIterateOnSourceAgain(self):

        # arrange
        iteratorMock = build_IteratorMock(range(10))
        slicedIterator = islice_extended(iteratorMock, None)
        list(slicedIterator)    # consume the whole iterator
        iteratorMock.__next__.call_count = 0

        # assert
        with self.assertRaises(StopIteration):
            # act
            next(slicedIterator)

        # assert
        self.assertEqual(iteratorMock.__next__.call_count, 0)

    def test_withStartStopStep_noIterationBeforeConsumption(self):
        for index, (iterable, start, stop, step) in enumerate(itertools.product(
            [range(0), range(10)],                              # iterable
            [None, -15, -10, -9, -4, -1, 0, 1, 4, 9, 10, 15],   # start
            [None, -15, -10, -9, -4, -1, 0, 1, 4, 9, 10, 15],   # stop
            [None, -7, -3, -1, 1, 3, 7],                        # step
        )):
            # remove nullcontext() for more details...but pay a dear execution time price in VSCode
            with nullcontext() or self.subTest(f"index:{index:04d} iterable:{iterable} start:{start} stop:{stop} step:{step}"):

                # arrange
                iteratorMock = build_IteratorMock(iterable)

                # act
                islice_extended(iteratorMock, start, stop, step)

                # assert
                self.assertEqual(iteratorMock.__next__.call_count, 0)

    def test_withStartStopStep_iterateAsExpectedOnFirstConsumption_readable(self):
        for index, (iterableSize, start, stop, step, expectedCallCount) in enumerate([
            # fmt: off
            # regular cases
            [10,    4,    7,  1,  4+1],
            [10,    4,    7,  2,  4+1],
            [10,    4,    4,  5,    4],
            [10,    9,   10,  1,  9+1],

            # negative start/stop => need the whole content
            [10,   -1,   10,  1, 11],
            [10,    1,  -10,  1, 11],

            # negative step => need to iterate until element with start index included
            [10,    3,   1, -1, 3+1],

            # guaranteed empty result...but still iterate over the source to keep it simple for the caller
            [10,    4,   6, -1,   5],   # negative step => iterate until element with start index included
            [10,    6,   4,  1,   6],   # itertools.islice behavior
            [10,   -4,  -6,  1,  11],   # negative start/stop => need the whole content
            [10,   -6,  -4, -1,  11],   # negative start/stop => need the whole content
            # fmt: on
        ]):
            # remove nullcontext() for more details...but pay a dear execution time price in VSCode
            with nullcontext() or self.subTest(f"index:{index:04d} iterableSize:{iterableSize} start:{start} stop:{stop} step:{step} expectedCallCount:{expectedCallCount}"):

                # arrange
                iteratorMock = build_IteratorMock(range(iterableSize))
                iteratorFromSlice = islice_extended(iteratorMock, start, stop, step)

                # act
                try:
                    next(iteratorFromSlice)
                except StopIteration:
                    pass

                # assert
                self.assertEqual(iteratorMock.__next__.call_count, expectedCallCount)

    def test_withStartStopStep_iterateAsExpectedOnFirstConsumption_extensive(self):
        for index, (iterableSize, start, stop, step) in enumerate(itertools.product(
            [0, 10],                                            # iterableSize
            [None, -15, -10, -9, -4, -1, 0, 1, 4, 9, 10, 15],   # start
            [None, -15, -10, -9, -4, -1, 0, 1, 4, 9, 10, 15],   # stop
            [None, -7, -3, -1, 1, 3, 7],                        # step
        )):
            # remove nullcontext() for more details...but pay a dear execution time price in VSCode
            with nullcontext() or self.subTest(f"index:{index:04d} iterableSize:{iterableSize} start:{start} stop:{stop} step:{step}"):

                # arrange
                iteratorMock = build_IteratorMock(range(iterableSize))
                iteratorFromSlice = islice_extended(iteratorMock, start, stop, step)
                expectedCallCount = expectedIterationsForNElements(iterableSize, start, stop, step, numberOfElements=1)

                # act
                try:
                    next(iteratorFromSlice)
                except StopIteration:
                    pass

                # assert
                self.assertEqual(iteratorMock.__next__.call_count, expectedCallCount)

    def test_withStartStopStep_iterateAsExpectedOnFullConsumption_readable(self):
        for index, (iterableSize, start, stop, step, expectedCallCount) in enumerate([
            # fmt: off
            # regular cases
            [10,    4,    7,  1,  7],   # max(start, stop) iterations
            [10,    4,    7,  2,  7],   # max(start, stop) iterations
            [10,    4,    4,  5,  4],   # max(start, stop) iterations
            [10,    9,   10,  1, 10],   # max(start, stop) iterations

            # negative start/stop => need the whole content
            [10,   -1,   10,  1, 11],
            [10,    1,  -10,  1, 11],

            # negative step => need to iterate until element with start index included
            [10,    3,    1, -1, 3+1],
            [10,    3, None, -1, 3+1],

            # guaranteed empty result...but still iterate over the source to keep it simple for the caller
            [10,    4,    6, -1,   5],   # negative step => iterate until element with start index included
            [10,    6,    4,  1,   6],   # itertools.islice behavior
            [10,   -4,   -6,  1,  11],   # negative start/stop => need the whole content
            [10,   -6,   -4, -1,  11],   # negative start/stop => need the whole content
            # fmt: on
        ]):
            # remove nullcontext() for more details...but pay a dear execution time price in VSCode
            with nullcontext() or self.subTest(f"index:{index:04d} iterableSize:{iterableSize} start:{start} stop:{stop} step:{step} expectedCallCount:{expectedCallCount}"):

                # arrange
                iteratorMock = build_IteratorMock(range(iterableSize))
                iteratorFromSlice = islice_extended(iteratorMock, start, stop, step)

                # act
                list(iteratorFromSlice)

                # assert
                self.assertEqual(iteratorMock.__next__.call_count, expectedCallCount)

    def test_withStartStopStep_iterateAsExpectedOnFullConsumption_extensive(self):
        for index, (iterableSize, start, stop, step) in enumerate(itertools.product(
            [0, 10],                                            # iterableSize
            [None, -15, -10, -9, -4, -1, 0, 1, 4, 9, 10, 15],   # start
            [None, -15, -10, -9, -4, -1, 0, 1, 4, 9, 10, 15],   # stop
            [None, -7, -3, -1, 1, 3, 7],                        # step
        )):
            # remove nullcontext() for more details...but pay a dear execution time price in VSCode
            with nullcontext() or self.subTest(f"index:{index:04d} iterableSize:{iterableSize} start:{start} stop:{stop} step:{step}"):

                # arrange
                iteratorMock = build_IteratorMock(range(iterableSize))
                iteratorFromSlice = islice_extended(iteratorMock, start, stop, step)
                expectedCallCount = expectedIterationsForNElements(iterableSize, start, stop, step)

                # act
                list(iteratorFromSlice)

                # assert
                self.assertEqual(iteratorMock.__next__.call_count, expectedCallCount)

    def test_withStartStopStepWithSingleConsumption_releaseItemsReferences_readable(self):
        for index, (start, stop, step, expectedWeakReferencesValidity) in enumerate([
            # fmt: off
            # regular cases
            [ 4,    7,  1, [0, 0, 0, 0, 0, 1, 1, 1, 1, 1]],   # noqa: E201
            [ 4,    7,  2, [0, 0, 0, 0, 0, 1, 1, 1, 1, 1]],   # noqa: E201
            [ 4,    4,  5, [0, 0, 0, 0, 1, 1, 1, 1, 1, 1]],   # noqa: E201
            [ 9,   10,  1, [0, 0, 0, 0, 0, 0, 0, 0, 0, 0]],   # noqa: E201

            # # negative start/stop => need the whole content
            [-1,   10,  1, [0, 0, 0, 0, 0, 0, 0, 0, 0, 0]],   # noqa: E201
            [ 1,  -10,  1, [0, 0, 0, 0, 0, 0, 0, 0, 0, 0]],   # noqa: E201

            # # negative step => need to iterate until element with start index included
            [ 3,    1, -1, [0, 0, 1, 0, 1, 1, 1, 1, 1, 1]],   # noqa: E201
            [ 3, None, -1, [1, 1, 1, 0, 1, 1, 1, 1, 1, 1]],   # noqa: E201
            [ 6, None, -2, [1, 0, 1, 0, 1, 0, 0, 1, 1, 1]],   # noqa: E201

            # # guaranteed empty result...but still iterate over the source to keep it simple for the caller
            [ 4,    6, -1, [0, 0, 0, 0, 0, 1, 1, 1, 1, 1]],   # negative step => iterate until element with start index included   # noqa: E201
            [ 6,    4,  1, [0, 0, 0, 0, 0, 0, 1, 1, 1, 1]],   # itertools.islice behavior                                          # noqa: E201
            [-4,   -6,  1, [0, 0, 0, 0, 0, 0, 0, 0, 0, 0]],   # negative start/stop => need the whole content                      # noqa: E201
            [-6,   -4, -1, [0, 0, 0, 0, 0, 0, 0, 0, 0, 0]],   # negative start/stop => need the whole content                      # noqa: E201
            # fmt: on
        ]):
            # remove nullcontext() for more details...but pay a dear execution time price in VSCode
            with nullcontext() or self.subTest(f"index:{index:04d} start:{start} stop:{stop} step:{step}"):

                # arrange
                iteratorSize = 10
                iterator = IteratorWithWeakReferences.FROM_SIZE(size=iteratorSize)

                # act
                islice_iterator = islice_extended(iterator, start, stop, step)
                try:
                    next(islice_iterator)
                except StopIteration:
                    pass

                # assert
                # converting list[bool] to list[int] for readability in case of failure
                self.assertListEqual(expectedWeakReferencesValidity, list(map(int, iterator.weakReferencesState())))

    def test_withStartStopStepWithSingleConsumption_releaseItemsReferences_extensive(self):
        for index, (start, stop, step) in enumerate(itertools.product(
            [None, -15, -10, -9, -4, -1, 0, 1, 4, 9, 10, 15],   # start
            [None, -15, -10, -9, -4, -1, 0, 1, 4, 9, 10, 15],   # stop
            [None, -7, -3, -1, 1, 3, 7],                        # step
        )):
            # remove nullcontext() for more details...but pay a dear execution time price in VSCode
            with nullcontext() or self.subTest(f"index:{index:04d} start:{start} stop:{stop} step:{step}"):

                # arrange
                iteratorSize = 10
                iterator = IteratorWithWeakReferences.FROM_SIZE(size=iteratorSize)
                expectedConsumedElements = expectedIterationsForNElements(iteratorSize, start, stop, step, numberOfElements=1)
                expectedReturnedIndexes = set(list(range(10))[start:stop:step][1:None])
                expectedWeakReferencesValidity = list(map(lambda index: int(index in expectedReturnedIndexes) if index < expectedConsumedElements else 1, range(iteratorSize)))

                # act
                islice_iterator = islice_extended(iterator, start, stop, step)
                try:
                    next(islice_iterator)
                except StopIteration:
                    pass

                # assert
                # converting list[bool] to list[int] for readability in case of failure
                self.assertListEqual(expectedWeakReferencesValidity, list(map(int, iterator.weakReferencesState())))

    def test_withStartStopStepWithFullConsumption_releaseItemsReferences_readable(self):
        for index, (start, stop, step, expectedWeakReferencesValidity) in enumerate([
            # fmt: off
            # regular cases
            [ 4,    7,  1, [0, 0, 0, 0, 0, 0, 0, 1, 1, 1]],  # max(start, stop) iterations     # noqa: E201
            [ 4,    7,  2, [0, 0, 0, 0, 0, 0, 0, 1, 1, 1]],  # max(start, stop) iterations     # noqa: E201
            [ 4,    4,  5, [0, 0, 0, 0, 1, 1, 1, 1, 1, 1]],  # max(start, stop) iterations     # noqa: E201
            [ 9,   10,  1, [0, 0, 0, 0, 0, 0, 0, 0, 0, 0]],  # max(start, stop) iterations     # noqa: E201

            # # negative start/stop => need the whole content
            [-1,   10,  1, [0, 0, 0, 0, 0, 0, 0, 0, 0, 0]],  # noqa: E201
            [ 1,  -10,  1, [0, 0, 0, 0, 0, 0, 0, 0, 0, 0]],  # noqa: E201

            # # negative step => need to iterate until element with start index included
            [ 3,    1, -1, [0, 0, 0, 0, 1, 1, 1, 1, 1, 1]],  # noqa: E201
            [ 3, None, -1, [0, 0, 0, 0, 1, 1, 1, 1, 1, 1]],  # noqa: E201
            [ 6, None, -2, [0, 0, 0, 0, 0, 0, 0, 1, 1, 1]],  # noqa: E201

            # # guaranteed empty result...but still iterate over the source to keep it simple for the caller
            [ 4,    6, -1, [0, 0, 0, 0, 0, 1, 1, 1, 1, 1]],  # negative step => iterate until element with start index included   # noqa: E201
            [ 6,    4,  1, [0, 0, 0, 0, 0, 0, 1, 1, 1, 1]],  # itertools.islice behavior                                          # noqa: E201
            [-4,   -6,  1, [0, 0, 0, 0, 0, 0, 0, 0, 0, 0]],  # negative start/stop => need the whole content                      # noqa: E201
            [-6,   -4, -1, [0, 0, 0, 0, 0, 0, 0, 0, 0, 0]],  # negative start/stop => need the whole content                      # noqa: E201
            # fmt: on
        ]):
            # remove nullcontext() for more details...but pay a dear execution time price in VSCode
            with nullcontext() or self.subTest(f"index:{index:04d} start:{start} stop:{stop} step:{step}"):

                # arrange
                iteratorSize = 10
                iterator = IteratorWithWeakReferences.FROM_SIZE(size=iteratorSize)

                # act
                islice_iterator = islice_extended(iterator, start, stop, step)
                list(islice_iterator)

                # assert
                # converting list[bool] to list[int] for readability in case of failure
                self.assertListEqual(expectedWeakReferencesValidity, list(map(int, iterator.weakReferencesState())))

    def test_withStartStopStepWithFullConsumption_releaseItemsReferences_extensive(self):
        for index, (start, stop, step) in enumerate(itertools.product(
            [None, -15, -10, -9, -4, -1, 0, 1, 4, 9, 10, 15],   # start
            [None, -15, -10, -9, -4, -1, 0, 1, 4, 9, 10, 15],   # stop
            [None, -7, -3, -1, 1, 3, 7],                        # step
        )):
            # remove nullcontext() for more details...but pay a dear execution time price in VSCode
            with nullcontext() or self.subTest(f"index:{index:04d} start:{start} stop:{stop} step:{step}"):

                # arrange
                iteratorSize = 10
                iterator = IteratorWithWeakReferences.FROM_SIZE(size=iteratorSize)
                expectedConsumedElements = expectedIterationsForNElements(iteratorSize, start, stop, step)
                expectedWeakReferencesValidity = list(map(lambda index: int(index >= expectedConsumedElements), range(iteratorSize)))

                # act
                islice_iterator = islice_extended(iterator, start, stop, step)
                list(islice_iterator)

                # assert
                # converting list[bool] to list[int] for readability in case of failure
                self.assertListEqual(expectedWeakReferencesValidity, list(map(int, iterator.weakReferencesState())))

    def test_elements_lifecycle(self):
        class TestCase(NamedTuple):
            initialSize: int
            slice: int
            # list of expected intermediate elements states (alive or not)
            # during a complete iteration
            expectedAliveStates: list[list[int]]

        # fmt: off
        testCases = [
            # testcases for: start>0, stop>0, step>0
            TestCase(initialSize=3, slice=(None, None, 1), expectedAliveStates=[  # noqa: E501
                [1, 1, 1], [0, 1, 1], [0, 0, 1], [0, 0, 0], [0, 0, 0]]),
            TestCase(initialSize=3, slice=(0, None, 1), expectedAliveStates=[
                [1, 1, 1], [0, 1, 1], [0, 0, 1], [0, 0, 0], [0, 0, 0]]),
            TestCase(initialSize=3, slice=(1, 2, 1), expectedAliveStates=[
                [1, 1, 1], [0, 0, 1], [0, 0, 1]]),
            TestCase(initialSize=4, slice=(0, None, 2), expectedAliveStates=[
                [1, 1, 1, 1], [0, 1, 1, 1], [0, 0, 0, 1], [0, 0, 0, 0]]),
            TestCase(initialSize=5, slice=(1, 4, 2), expectedAliveStates=[
                [1, 1, 1, 1, 1], [0, 0, 1, 1, 1], [0, 0, 0, 0, 1], [0, 0, 0, 0, 1]]),  # noqa: E501
            TestCase(initialSize=5, slice=(4, 1, 1), expectedAliveStates=[
                [1, 1, 1, 1, 1], [0, 0, 0, 0, 1]]),

            # FYI: to process a negative start/stop index, we need to iterate
            # on the whole iterator. All the elements will be consumed
            # and will ALWAYS be released on full iteration completion.

            # testcases for: start<0, stop>0, step>0
            TestCase(initialSize=3, slice=(-3, None, 1), expectedAliveStates=[
                [1, 1, 1], [0, 1, 1], [0, 0, 1], [0, 0, 0], [0, 0, 0]]),
            TestCase(initialSize=3, slice=(-2, 2, 1), expectedAliveStates=[
                [1, 1, 1], [0, 0, 0], [0, 0, 0]]),
            TestCase(initialSize=4, slice=(-4, None, 2), expectedAliveStates=[
                [1, 1, 1, 1], [0, 0, 1, 0], [0, 0, 0, 0], [0, 0, 0, 0]]),
            TestCase(initialSize=5, slice=(-4, 4, 2), expectedAliveStates=[
                [1, 1, 1, 1, 1], [0, 0, 0, 1, 0], [0, 0, 0, 0, 0], [0, 0, 0, 0, 0]]),  # noqa: E501
            TestCase(initialSize=3, slice=(-2, 0, 1), expectedAliveStates=[
                [1, 1, 1], [0, 0, 0]]),

            # testcases for: start>0, stop<0, step>0
            TestCase(initialSize=3, slice=(None, -1, 1), expectedAliveStates=[
                [1, 1, 1], [0, 1, 0], [0, 0, 0], [0, 0, 0]]),
            TestCase(initialSize=4, slice=(1, -1, 1), expectedAliveStates=[
                [1, 1, 1, 1], [0, 0, 1, 0], [0, 0, 0, 0], [0, 0, 0, 0]]),
            TestCase(initialSize=5, slice=(None, -2, 2), expectedAliveStates=[
                [1, 1, 1, 1, 1], [0, 0, 1, 0, 0], [0, 0, 0, 0, 0], [0, 0, 0, 0, 0]]),  # noqa: E501
            TestCase(initialSize=5, slice=(1, -1, 2), expectedAliveStates=[
                [1, 1, 1, 1, 1], [0, 0, 0, 1, 0], [0, 0, 0, 0, 0], [0, 0, 0, 0, 0]]),  # noqa: E501
            TestCase(initialSize=5, slice=(4, -5, 2), expectedAliveStates=[
                [1, 1, 1, 1, 1], [0, 0, 0, 0, 0]]),

            # testcases for: start>0, stop>0, step<0
            TestCase(initialSize=3, slice=(None, None, -1), expectedAliveStates=[  # noqa: E501
                [1, 1, 1], [1, 1, 0], [1, 0, 0], [0, 0, 0], [0, 0, 0]]),
            TestCase(initialSize=3, slice=(2, None, -1), expectedAliveStates=[
                [1, 1, 1], [1, 1, 0], [1, 0, 0], [0, 0, 0], [0, 0, 0]]),
            TestCase(initialSize=3, slice=(None, 0, -1), expectedAliveStates=[
                [1, 1, 1], [0, 1, 0], [0, 0, 0], [0, 0, 0]]),
            TestCase(initialSize=6, slice=(3, 1, -1), expectedAliveStates=[
                [1, 1, 1, 1, 1, 1], [0, 0, 1, 0, 1, 1], [0, 0, 0, 0, 1, 1], [0, 0, 0, 0, 1, 1]]),  # noqa: E501
            TestCase(initialSize=5, slice=(1, 3, -1), expectedAliveStates=[
                [1, 1, 1, 1, 1], [0, 0, 1, 1, 1]]),

            # testcases for: start<0, stop>0, step<0
            TestCase(initialSize=3, slice=(-1, None, -1), expectedAliveStates=[
                [1, 1, 1], [1, 1, 0], [1, 0, 0], [0, 0, 0], [0, 0, 0]]),
            TestCase(initialSize=3, slice=(-1, 0, -1), expectedAliveStates=[
                [1, 1, 1], [0, 1, 0], [0, 0, 0], [0, 0, 0]]),
            TestCase(initialSize=6, slice=(-2, None, -2), expectedAliveStates=[
                [1, 1, 1, 1, 1, 1], [1, 0, 1, 0, 0, 0], [1, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0]]),  # noqa: E501
            TestCase(initialSize=6, slice=(-2, 1, -2), expectedAliveStates=[
                [1, 1, 1, 1, 1, 1], [0, 0, 1, 0, 0, 0], [0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0]]),  # noqa: E501
            TestCase(initialSize=6, slice=(-4, 4, -2), expectedAliveStates=[
                [1, 1, 1, 1, 1, 1], [0, 0, 0, 0, 0, 0]]),

            # testcases for: start>0, stop<0, step<0
            TestCase(initialSize=3, slice=(None, -3, -1), expectedAliveStates=[
                [1, 1, 1], [0, 1, 0], [0, 0, 0], [0, 0, 0]]),
            TestCase(initialSize=3, slice=(None, -4, -1), expectedAliveStates=[
                [1, 1, 1], [1, 1, 0], [1, 0, 0], [0, 0, 0], [0, 0, 0]]),
            TestCase(initialSize=5, slice=(3, -4, -1), expectedAliveStates=[
                [1, 1, 1, 1, 1], [0, 0, 1, 0, 0], [0, 0, 0, 0, 0], [0, 0, 0, 0, 0]]),   # noqa: E501
            TestCase(initialSize=5, slice=(1, -1, -1), expectedAliveStates=[
                [1, 1, 1, 1, 1], [0, 0, 0, 0, 0]]),
        ]
        # fmt: on

        for index, testCase in enumerate(testCases):
            with self.subTest(f"{index:02d}", testCase=testCase):
                iterator = IteratorWithWeakReferences.FROM_SIZE(
                    testCase.initialSize
                )
                islice_iterator = islice_extended(iterator, *testCase.slice)

                aliveStates = []
                # initial alive states
                aliveStates.append(iterator.weakReferencesState())
                while True:
                    try:
                        next(islice_iterator)
                        # intermediate alive states
                        aliveStates.append(iterator.weakReferencesState())
                    except StopIteration:
                        # final alive states
                        aliveStates.append(iterator.weakReferencesState())
                        break
                self.assertEqual(aliveStates, testCase.expectedAliveStates)


if __name__ == '__main__':
    unittest.main(verbosity=2)
