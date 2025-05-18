import itertools
import unittest
from contextlib import nullcontext
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
            [10,    4,    7,  1,  7],
            [10,    4,    7,  2,  7],

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


if __name__ == '__main__':
    unittest.main(verbosity=2)
