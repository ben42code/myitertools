import gc
import itertools
import unittest
import weakref
from abc import abstractmethod
from contextlib import nullcontext
from typing import Callable, Generator, Generic, Iterable, Iterator, NamedTuple, SupportsIndex, TypeVar
from unittest.mock import Mock

from ben42code.myitertools import StreamSequence, islice_extended

T = TypeVar('T')


def preloadData(stream: StreamSequence, preload: int) -> None:
    # Preload exactly `preload` values into the cache via integer indexing,
    # avoiding the transient sub-iterator that list(stream[:preload]) would
    # leave in the WeakSet (non-deterministic on PyPy).
    if preload <= 0:
        return
    try:
        stream[preload - 1]
    except IndexError:
        pass


class IterableWrapper:
    def __init__(self, iterable: Iterable):
        assert isinstance(iterable, Iterable)
        self._iterator = IteratorWrapper(iter(iterable))

    def __iter__(self) -> Iterator:
        return self._iterator


class IteratorWrapper:
    def __init__(self, iterator: Iterator):
        assert isinstance(iterator, Iterator)
        self._iterator = iterator

    def __iter__(self):
        return self

    def __next__(self):
        return next(self._iterator)


def incrementalValuesGenerator(value: int = 0):
    yield from itertools.count(start=value)


def valuesGenerator(values):
    yield from values


def build_IteratorMock(side_effect) -> Mock:
    IteratorMock = Mock()
    IteratorMock.__iter__ = Mock(return_value=IteratorMock)
    IteratorMock.__next__ = Mock(side_effect=side_effect)

    return IteratorMock


def FirstNotNone(*args):
    return next(filter(lambda x: x is not None, args))


def iterableGenerators(size: int = 5) -> Iterable[Callable[[int], Iterable[int]]]:
    # use alias for main size parameter to not conflict with the lambda size parameter
    iterableSize = size

    yield from [
        lambda size=None: valuesGenerator(range(FirstNotNone(size, iterableSize))),
        lambda size=None: IterableWrapper(range(FirstNotNone(size, iterableSize))),
        lambda size=None: IteratorWrapper(iter(range(FirstNotNone(size, iterableSize)))),
    ]


class StateTester:
    def __init__(self, iterableGenerator: Callable[[int], Iterable] = lambda size: range(size)) -> None:
        assert iterableGenerator is not None
        self._iterableGenerator = iterableGenerator

    def setup(self,
              testCase: unittest.TestCase,
              initialDataSize: int,
              cachedBefore: int = 0,
              skippedBefore: int = 0,
              cachedAfter: int | None = None,   # if not define, will fallback to "before" value
              skippedAfter: int | None = None,  # if not define, will fallback to "before" value
              ) -> None:

        self._testCase = testCase
        self._initialDataSize = initialDataSize
        self._cachedBefore = cachedBefore
        self._skippedBefore = skippedBefore
        self._cachedAfter = FirstNotNone(cachedAfter, self._cachedBefore)
        self._skippedAfter = FirstNotNone(skippedAfter, self._skippedBefore)

        # Amount of cached data can only decrease if you skip data
        assert self._cachedAfter >= max(0, self._cachedBefore - (self._skippedAfter - self._skippedBefore))
        # Amount of Skipped data can only increase
        assert self._skippedAfter >= self._skippedBefore

    def _generateIterable(self) -> Iterable:
        return self._iterableGenerator(size=self._initialDataSize)

    def arrangeStep(self) -> StreamSequence:
        self._iterable = self._generateIterable()
        stream = StreamSequence(self._iterable)
        self.stream = stream
        self.stream.consume(self._skippedBefore)
        preloadData(stream=self.stream, preload=self._cachedBefore)
        return self.stream

    @abstractmethod
    def assertStep(self) -> None:
        pass


class StateTester_ExpectedData(StateTester):
    @property
    def _expectedData(self) -> list:
        return list(range(self._skippedAfter, self._initialDataSize))


class StateTester_ExpectedDataFromIteration(StateTester_ExpectedData):
    def assertStep(self) -> None:
        values = [value for value in self.stream]
        self._testCase.assertEqual(values, self._expectedData)


class StateTester_ExpectedDataFromGetItem(StateTester_ExpectedData):
    def assertStep(self) -> None:
        values = []
        for index in itertools.count():
            try:
                values.append(self.stream[index])
            except IndexError:
                break
        self._testCase.assertEqual(values, self._expectedData)


class StateTester_ExpectedDataFromSlice(StateTester_ExpectedData):
    def assertStep(self) -> None:
        values = list(self.stream[:])
        self._testCase.assertEqual(values, self._expectedData)


class StateTester_CacheSize(StateTester):
    def _generateIterable(self) -> Iterable:
        iterable = super(StateTester_CacheSize, self)._generateIterable()
        self.iteratorMock = build_IteratorMock(iterable)
        return self.iteratorMock

    def assertStep(self) -> None:
        self.iteratorMock.__next__.reset_mock()
        itr = iter(self.stream)
        [next(itr) for _ in range(self._initialDataSize - self._skippedAfter)]
        self._testCase.assertEqual(self.iteratorMock.__next__.call_count, self._initialDataSize - self._skippedAfter - self._cachedAfter)


class StateTester_PositiveIndexError(StateTester):
    def assertStep(self) -> None:
        with self._testCase.assertRaises(IndexError):
            self.stream[self._initialDataSize - self._skippedAfter]


class StateTester_NegativeIndexError(StateTester):
    def assertStep(self) -> None:
        with self._testCase.assertRaises(IndexError):
            self.stream[-(self._initialDataSize - self._skippedAfter + 1)]


class StateTesterGenerators:

    def __init__(self, light: bool = False) -> None:

        validators = []
        itrGenerators = iterableGenerators() if not light else [lambda size: range(size)]
        # add expected data tester with different kind of iterable
        for iterableGenerator in itrGenerators:
            validators.append(lambda: StateTester_ExpectedDataFromIteration(iterableGenerator=iterableGenerator))
            validators.append(lambda: StateTester_ExpectedDataFromGetItem(iterableGenerator=iterableGenerator))
            validators.append(lambda: StateTester_ExpectedDataFromSlice(iterableGenerator=iterableGenerator))
            validators.append(lambda: StateTester_PositiveIndexError(iterableGenerator=iterableGenerator))
            validators.append(lambda: StateTester_NegativeIndexError(iterableGenerator=iterableGenerator))

        validators.append(lambda: StateTester_CacheSize())

        self.resultingStateValidators = validators

    def __iter__(self) -> Iterator[Callable[[], StateTester]]:
        return iter(self.resultingStateValidators)


def sliceTestCases() -> Generator[slice, None, None]:

    for (start, stop, step) in itertools.product(
        [None, -3, 3, 15],   # start
        [None, -3, 3, 15],   # stop
        [None, -2, -1, 1, 2]       # step
    ):
        yield slice(start, stop, step)


def sliceTestCasesLight() -> Generator[slice, None, None]:

    for (start, stop, step) in itertools.product(
        [None, -3, 3],   # start
        [None, -3, 3],   # stop
        [-2, -1, 1, 2]   # step
    ):
        yield slice(start, stop, step)


class AdvanceOperation(NamedTuple):
    name: str
    apply: Callable[["StreamSequence[int]", "int | None"], "list[int] | None"]
    expectedReturn: Callable[[list[int]], "list[int] | None"]


def advanceOperations() -> list[AdvanceOperation]:
    # The two public ways to advance the visible front, treated as black boxes.
    # `apply(stream, n)` performs the advance; `expectedReturn(advanced)` is the
    # method's documented return for the values it advanced past.
    return [
        AdvanceOperation(name="take", apply=lambda stream, n: stream.take(n), expectedReturn=lambda advanced: advanced),
        AdvanceOperation(name="consume", apply=lambda stream, n: stream.consume(n), expectedReturn=lambda advanced: None),
    ]


class IteratorSliceHelper(Generic[T]):

    @classmethod
    def FROM(cls, iterableSize: int):
        iteratorMock = build_IteratorMock(range(iterableSize))
        return cls(iterator=iteratorMock, iterableSize=iterableSize, mock=iteratorMock)

    def __init__(self, iterator: Iterator[T], iterableSize: int = None, mock: Mock = None):
        self._iterator = iterator
        self._mock = mock
        self._iterableSize = iterableSize

    @property
    def nextCallsCount(self):
        assert self._mock is not None
        assert self._iterableSize is not None
        assert self._mock.__next__.call_count <= self._iterableSize + 1

        return self._mock.__next__.call_count

    def __getitem__(self, key: slice | SupportsIndex) -> "IteratorSliceHelper[T] | T":
        if isinstance(key, slice):
            keySlice: slice = key
            iterator = islice_extended(self._iterator, keySlice.start, keySlice.stop, keySlice.step)
            return IteratorSliceHelper(iterator=iterator)
        elif isinstance(key, SupportsIndex):
            keyIndex = key.__index__()
            if keyIndex >= 0:
                for _ in range(keyIndex + 1):
                    try:
                        value = next(self._iterator)
                    except StopIteration:
                        raise IndexError
                return value
            else:
                data = list(self._iterator)
                return data[keyIndex]
        else:
            assert False


class ValueFromSliceTestCase(NamedTuple):
    testCase: Callable[[Iterable[T]], T]


def inRangeValueFromSliceTestCases() -> Iterable[ValueFromSliceTestCase]:
    yield from [
        # regular cases (positive index)
        ValueFromSliceTestCase(testCase=lambda itr: itr[0:10][0]),
        ValueFromSliceTestCase(testCase=lambda itr: itr[0:10][5]),
        ValueFromSliceTestCase(testCase=lambda itr: itr[0:10][9]),

        # regular cases (negative index)
        ValueFromSliceTestCase(testCase=lambda itr: itr[0:10][-10]),
        ValueFromSliceTestCase(testCase=lambda itr: itr[0:10][-5]),
        ValueFromSliceTestCase(testCase=lambda itr: itr[0:10][-1]),

        # positive step from start
        ValueFromSliceTestCase(testCase=lambda itr: itr[0:10:2][3]),
        ValueFromSliceTestCase(testCase=lambda itr: itr[0:10:3][2]),
        ValueFromSliceTestCase(testCase=lambda itr: itr[0:10:2][-3]),
        ValueFromSliceTestCase(testCase=lambda itr: itr[0:10:3][-1]),

        # positive step from offset
        ValueFromSliceTestCase(testCase=lambda itr: itr[2:10:2][3]),
        ValueFromSliceTestCase(testCase=lambda itr: itr[2:10:3][2]),
        ValueFromSliceTestCase(testCase=lambda itr: itr[2:10:2][-3]),
        ValueFromSliceTestCase(testCase=lambda itr: itr[2:10:3][-1]),

        # negative step
        ValueFromSliceTestCase(testCase=lambda itr: itr[10:2:-2][3]),
        ValueFromSliceTestCase(testCase=lambda itr: itr[10:2:-3][2]),
        ValueFromSliceTestCase(testCase=lambda itr: itr[10:2:-2][-3]),
        ValueFromSliceTestCase(testCase=lambda itr: itr[10:2:-3][-1]),

        # negative step with None start
        ValueFromSliceTestCase(testCase=lambda itr: itr[None:2:-2][3]),
        ValueFromSliceTestCase(testCase=lambda itr: itr[None:2:-3][2]),
        ValueFromSliceTestCase(testCase=lambda itr: itr[None:2:-2][-3]),
        ValueFromSliceTestCase(testCase=lambda itr: itr[None:2:-3][-1]),

        # negative step with None stop
        ValueFromSliceTestCase(testCase=lambda itr: itr[9:None:-2][0]),
        ValueFromSliceTestCase(testCase=lambda itr: itr[9:None:-2][-1]),
        ValueFromSliceTestCase(testCase=lambda itr: itr[9:None:-3][0]),
        ValueFromSliceTestCase(testCase=lambda itr: itr[9:None:-3][-1]),

        # None stop (open-ended)
        ValueFromSliceTestCase(testCase=lambda itr: itr[0:None][0]),
        ValueFromSliceTestCase(testCase=lambda itr: itr[0:None][3]),
        ValueFromSliceTestCase(testCase=lambda itr: itr[0:None][9]),
        ValueFromSliceTestCase(testCase=lambda itr: itr[0:None][-10]),
        ValueFromSliceTestCase(testCase=lambda itr: itr[0:None][-7]),
        ValueFromSliceTestCase(testCase=lambda itr: itr[0:None][-1]),

        # None stop with positive step
        ValueFromSliceTestCase(testCase=lambda itr: itr[0:None:2][3]),
        ValueFromSliceTestCase(testCase=lambda itr: itr[0:None:3][2]),
        ValueFromSliceTestCase(testCase=lambda itr: itr[0:None:2][-3]),
        ValueFromSliceTestCase(testCase=lambda itr: itr[0:None:3][-1]),

        # None stop with positive step from offset
        ValueFromSliceTestCase(testCase=lambda itr: itr[2:None:2][3]),
        ValueFromSliceTestCase(testCase=lambda itr: itr[2:None:3][2]),
        ValueFromSliceTestCase(testCase=lambda itr: itr[2:None:2][-3]),
        ValueFromSliceTestCase(testCase=lambda itr: itr[2:None:3][-1]),

        # None:None slice (full copy)
        ValueFromSliceTestCase(testCase=lambda itr: itr[:][0]),
        ValueFromSliceTestCase(testCase=lambda itr: itr[:][5]),
        ValueFromSliceTestCase(testCase=lambda itr: itr[:][9]),
        ValueFromSliceTestCase(testCase=lambda itr: itr[:][-1]),
        ValueFromSliceTestCase(testCase=lambda itr: itr[::2][0]),
        ValueFromSliceTestCase(testCase=lambda itr: itr[::2][3]),
        ValueFromSliceTestCase(testCase=lambda itr: itr[::2][-1]),
    ]


def outOfRangeValueFromSliceTestCases() -> Iterable[ValueFromSliceTestCase]:
    yield from [
        # just past the boundary (positive index)
        ValueFromSliceTestCase(testCase=lambda itr: itr[0:10][10]),
        ValueFromSliceTestCase(testCase=lambda itr: itr[1:9][8]),
        ValueFromSliceTestCase(testCase=lambda itr: itr[1:9:2][4]),

        # just past the boundary (negative index)
        ValueFromSliceTestCase(testCase=lambda itr: itr[0:10][-11]),
        ValueFromSliceTestCase(testCase=lambda itr: itr[1:9][-9]),
        ValueFromSliceTestCase(testCase=lambda itr: itr[1:9:2][-5]),

        # negative step
        ValueFromSliceTestCase(testCase=lambda itr: itr[9:1:-2][4]),
        ValueFromSliceTestCase(testCase=lambda itr: itr[9:1:-2][-5]),
        ValueFromSliceTestCase(testCase=lambda itr: itr[None:1:-2][4]),
        ValueFromSliceTestCase(testCase=lambda itr: itr[None:1:-2][-5]),
        ValueFromSliceTestCase(testCase=lambda itr: itr[9:None:-2][5]),
        ValueFromSliceTestCase(testCase=lambda itr: itr[9:None:-2][-6]),

        # None stop (open-ended)
        ValueFromSliceTestCase(testCase=lambda itr: itr[0:None][10]),
        ValueFromSliceTestCase(testCase=lambda itr: itr[0:None][-11]),
        ValueFromSliceTestCase(testCase=lambda itr: itr[1:None][9]),
        ValueFromSliceTestCase(testCase=lambda itr: itr[1:None][-10]),
        ValueFromSliceTestCase(testCase=lambda itr: itr[1:None:2][5]),
        ValueFromSliceTestCase(testCase=lambda itr: itr[1:None:2][-6]),

        # None:None slice (full copy)
        ValueFromSliceTestCase(testCase=lambda itr: itr[:][10]),
        ValueFromSliceTestCase(testCase=lambda itr: itr[:][- 11]),
        ValueFromSliceTestCase(testCase=lambda itr: itr[::2][5]),
        ValueFromSliceTestCase(testCase=lambda itr: itr[::2][-6]),

        # way out of range
        ValueFromSliceTestCase(testCase=lambda itr: itr[0:10][100]),
        ValueFromSliceTestCase(testCase=lambda itr: itr[0:10][-100]),

        # empty-result slice (any index is out of range)
        ValueFromSliceTestCase(testCase=lambda itr: itr[5:5][0]),
        ValueFromSliceTestCase(testCase=lambda itr: itr[5:5][-1]),
    ]


class StreamSequence_Test(unittest.TestCase):

    # ==== constructor ===

    def test_constructor_withSupportedTypes_returnsExpectedValue(self):

        for iterableGenerator in iterableGenerators():
            # arrange
            iterable = iterableGenerator()
            # remove nullcontext() for more details...but pay a dear execution time price in VSCode
            with nullcontext() or self.subTest(f"Iterable: {iterable}"):
                # act
                stream = StreamSequence(iterable)

                # assert
                data = list(stream)
                self.assertEqual(data, list(iterableGenerator()))

    def test_constructor_withNonSupportedTypes_raisesTypeError(self):
        # arrange
        class NotAnIterator:
            def __next__(self):
                return 10

        invalidInputs = [
            None,
            10,
            object(),
            NotAnIterator()
        ]

        for invalidInput in invalidInputs:
            # remove nullcontext() for more details...but pay a dear execution time price in VSCode
            with nullcontext() or self.subTest(f"invalidInput: {invalidInput}"):
                # assert
                with self.assertRaises(TypeError):
                    # act
                    StreamSequence(invalidInput)

    # ==== iter ===

    def test_iter_withEmptyIterator_alwaysRaisesStopIteration(self):
        for index, (skippedBefore, iterableGenerator) in enumerate(itertools.product(
            [0, 2],                 # skippedBefore
            iterableGenerators(),   # iterableGenerator
        )):
            iterable = iterableGenerator(size=skippedBefore)
            # remove nullcontext() for more details...but pay a dear execution time price in VSCode
            with nullcontext() or self.subTest(f"index: {index:04d} skippedBefore: {skippedBefore} iterable: {iterable}"):
                # arrange
                stream = StreamSequence(iterable)
                stream.consume(skippedBefore)
                iterator = iter(stream)

                for _ in range(2):
                    # assert
                    with self.assertRaises(StopIteration):
                        # act
                        next(iterator)

    def test_iter_withEmptyIterator_iterateOnSourceOnlyOnce(self):
        for skippedBefore in [0, 2]:
            # remove nullcontext() for more details...but pay a dear execution time price in VSCode
            with nullcontext() or self.subTest(f"skippedBefore: {skippedBefore}"):
                # arrange
                iteratorMock = build_IteratorMock(list(range(skippedBefore)))
                stream = StreamSequence(iteratorMock)
                stream.consume(skippedBefore)
                iterator = iter(stream)
                iteratorMock.__next__.reset_mock()

                # act1
                with self.assertRaises(StopIteration):
                    next(iterator)

                # assert1
                self.assertEqual(iteratorMock.__next__.call_count, 1)   # iterate on source once to get a StopIteration

                # arrange2
                iteratorMock.__next__.reset_mock()

                # act2
                with self.assertRaises(StopIteration):
                    next(iterator)

                # assert2
                self.assertEqual(iteratorMock.__next__.call_count, 0)   # source should not be iterated again after that

    def test_iter_withEmptyIterator_finalStateIsValid(self):
        for (index, (skippedBefore, stateTesterGenerator)) in enumerate(itertools.product(
            [0, 2],                     # skippedData
            StateTesterGenerators()     # stateTesters
        )):
            stateTester = stateTesterGenerator()
            # remove nullcontext() for more details...but pay a dear execution time price in VSCode
            with nullcontext() or self.subTest(f"index: {index:04d} skippedBefore: {skippedBefore} stateTester: {stateTester}"):
                # Arrange
                stateTester.setup(
                    testCase=self,
                    initialDataSize=skippedBefore,
                    skippedBefore=skippedBefore,
                )
                stream = stateTester.arrangeStep()
                stream.consume(skippedBefore)

                # act
                iterator = iter(stream)
                with self.assertRaises(StopIteration):
                    next(iterator)

                # Assert
                stream = stateTester.assertStep()

    def test_iter_withBasicIterators_returnsCorrectValues(self):
        for (index, (cachedBefore, skippedBefore, iterationCount, iterableGenerator, withConcurrentIterator)) in enumerate(itertools.product(
            [0, 2, 3, 4],           # cachedBefore
            [0, 1],                 # skippedBefore
            [3, 5],                 # iterationCount
            iterableGenerators(),   # iterableGenerator
            [False, True],          # withConcurrentIterator
        )):
            iterable = iterableGenerator(size=5 + skippedBefore)
            # remove nullcontext() for more details...but pay a dear execution time price in VSCode
            with nullcontext() or self.subTest(f"index: {index:04d}: cachedBefore: {cachedBefore} skippedBefore: {skippedBefore} iterationCount: {iterationCount} iterable: {iterable} withConcurrentIterator: {withConcurrentIterator}"):     # noqa: E501
                # arrange
                stream = StreamSequence(iterable)
                stream.consume(skippedBefore)                            # skippedBefore
                preloadData(stream=stream, preload=cachedBefore)    # cachedBefore

                # act
                iterator1 = iter(stream)
                if not withConcurrentIterator:
                    values_1 = [next(iterator1) for _ in range(iterationCount)]
                else:
                    iterator2 = iter(stream)
                    # iterate on both iterators at the same time...just for the fun of it
                    (values_1, values_2) = (list(values) for values in zip(*[(next(iterator1), next(iterator2)) for _ in range(iterationCount)]))

                # assert
                self.assertEqual(values_1, list(range(skippedBefore, skippedBefore + iterationCount)))
                if withConcurrentIterator:
                    self.assertEqual(values_2, list(range(skippedBefore, skippedBefore + iterationCount)))

    def test_iter_withBasicIterators_iterateOnSource(self):
        for (index, (cachedBefore, skippedBefore, iterationCount, withConcurrentIterator)) in enumerate(itertools.product(
            [0, 2, 3, 4],           # cachedBefore
            [0, 1],                 # skippedBefore
            [3, 5],                 # iterationCount
            [False, True],          # withConcurrentIterator
        )):
            # remove nullcontext() for more details...but pay a dear execution time price in VSCode
            with nullcontext() or self.subTest(f"index: {index:04d}: cachedBefore: {cachedBefore} skippedBefore: {skippedBefore} iterationCount: {iterationCount} withConcurrentIterator: {withConcurrentIterator}"):     # noqa: E501
                # arrange
                iteratorMock = build_IteratorMock(range(5 + skippedBefore))
                stream = StreamSequence(iteratorMock)
                stream.consume(skippedBefore)                            # skippedBefore
                preloadData(stream=stream, preload=cachedBefore)    # cachedBefore
                iteratorMock.__next__.reset_mock()

                # act
                iterator1 = iter(stream)
                if not withConcurrentIterator:
                    [next(iterator1) for _ in range(iterationCount)]
                else:
                    iterator2 = iter(stream)
                    [(next(iterator1), next(iterator2)) for _ in range(iterationCount)]

                # assert
                self.assertEqual(iteratorMock.__next__.call_count, max(iterationCount - cachedBefore, 0))

    def test_iter_withBasicIterators_finalStateIsValid(self):

        for (index, (cachedBefore, skippedBefore, iterationCount, stateTesterGenerator, withConcurrentIterator)) in enumerate(itertools.product(
            [0, 2, 3, 4],           # cachedBefore
            [0, 1],                 # skippedBefore
            [3, 5],                 # iterationCount
            StateTesterGenerators(),    # stateTester
            [False, True],              # withConcurrentIterator
        )):
            stateTester = stateTesterGenerator()
            # remove nullcontext() for more details...but pay a dear execution time price in VSCode
            with nullcontext() or self.subTest(f"index: {index:04d} cachedBefore: {cachedBefore} skippedBefore: {skippedBefore} iterationCount: {iterationCount} stateTester: {stateTester} withConcurrentIterator: {withConcurrentIterator}"):  # noqa: E501
                # arrange
                stateTester.setup(
                    testCase=self,
                    initialDataSize=skippedBefore + 5,
                    cachedBefore=cachedBefore,
                    skippedBefore=skippedBefore,
                    cachedAfter=cachedBefore + max(0, iterationCount - cachedBefore),   # iterationCount might add elements to the cache...if not already cached
                )
                stream = stateTester.arrangeStep()

                # act
                iterator1 = iter(stream)
                if not withConcurrentIterator:
                    [next(iterator1) for _ in range(iterationCount)]
                else:
                    iterator2 = iter(stream)
                    [(next(iterator1), next(iterator2)) for _ in range(iterationCount)]

                # assert
                stream = stateTester.assertStep()

    def test_iter_whenAtTheEnd_alwaysRaiseStopIteration(self):

        for (index, (cachedBefore, skippedBefore, iterableGenerator)) in enumerate(itertools.product(
            [0, 3],                 # cachedBefore
            [0, 2],                 # skippedBefore
            iterableGenerators(),   # iterableGenerator
        )):
            iterableSize = 5
            iterable = iterableGenerator(size=iterableSize + skippedBefore)
            # remove nullcontext() for more details...but pay a dear execution time price in VSCode
            with nullcontext() or self.subTest(f"index: {index:04d} cachedBefore: {cachedBefore} skippedBefore: {skippedBefore} iterable: {iterable}"):
                # arrange
                stream = StreamSequence(iterable)
                stream.consume(skippedBefore)                            # skippedBefore
                preloadData(stream=stream, preload=cachedBefore)    # cachedBefore
                iterator = iter(stream)
                [next(iterator) for _ in range(iterableSize)]

                for _ in range(2):
                    # assert
                    with self.assertRaises(StopIteration):
                        # act
                        next(iterator)

    def test_iter_whenAtTheEnd_iterateOnSourceOnlyOnce(self):

        for (index, (cachedBefore, skippedBefore)) in enumerate(itertools.product(
            [0, 3],  # cachedBefore
            [0, 2],  # skippedBefore
        )):

            # remove nullcontext() for more details...but pay a dear execution time price in VSCode
            with nullcontext() or self.subTest(f"index: {index:04d} cachedBefore: {cachedBefore} skippedBefore: {skippedBefore}"):
                iterableSize = 5

                # arrange1
                iteratorMock = build_IteratorMock(range(iterableSize + skippedBefore))
                stream = StreamSequence(iteratorMock)
                stream.consume(skippedBefore)                            # skippedBefore
                preloadData(stream=stream, preload=cachedBefore)    # cachedBefore
                iterator = iter(stream)
                [next(iterator) for _ in range(iterableSize)]
                iteratorMock.__next__.reset_mock()

                # act1
                with self.assertRaises(StopIteration):
                    next(iterator)

                # assert1
                self.assertEqual(iteratorMock.__next__.call_count, 1)

                # arrange2
                iteratorMock.__next__.reset_mock()

                # act2
                with self.assertRaises(StopIteration):
                    next(iterator)

                # assert1
                self.assertEqual(iteratorMock.__next__.call_count, 0)

    # ==== getItem with an Index ===

    def test_getItem_withInvalidKey_raisesTypeError(self):
        stream = StreamSequence(range(5))

        for index, (key, iterableGenerator) in enumerate(itertools.product(
            ["unsupported", None, 12.3],    # key
            iterableGenerators(),           # iterableGenerator
        )):
            iterable = iterableGenerator(size=100)
            # remove nullcontext() for more details...but pay a dear execution time price in VSCode
            with nullcontext() or self.subTest(f"index: {index:04d} key: {key} iterable: {iterable}"):
                # arrange
                stream = StreamSequence(iterable)

                # act
                # assert
                with self.assertRaises(TypeError):
                    stream[key]

    def test_getItem_withIndexOnEmptySource_raisesIndexError(self):
        for index, (skippedBefore, iterableGenerator, itemIndex) in enumerate(itertools.product(
            [0, 2],                 # skippedBefore
            iterableGenerators(),   # iterableGenerator
            [1, 0, -1],             # itemIndex
        )):
            iterable = iterableGenerator(size=skippedBefore)
            # remove nullcontext() for more details...but pay a dear execution time price in VSCode
            with nullcontext() or self.subTest(f"index: {index:04d} skippedBefore: {skippedBefore} iterable: {iterable} itemIndex: {itemIndex}"):
                # arrange
                stream = StreamSequence(iterable)
                stream.consume(skippedBefore)

                # assert
                with self.assertRaises(IndexError):
                    # act
                    stream[itemIndex]

    def test_getItem_withIndexOnEmptySource_iterateOnSourceOnce(self):
        for index, (skippedBefore, itemIndex) in enumerate(itertools.product(
            [0, 2],         # skippedBefore
            [1, 0, -1],     # itemIndex
        )):
            # remove nullcontext() for more details...but pay a dear execution time price in VSCode
            with nullcontext() or self.subTest(f"index: {index:04d} skippedBefore: {skippedBefore} itemIndex: {itemIndex}"):
                # arrange
                iteratorMock = build_IteratorMock(range(skippedBefore))
                stream = StreamSequence(iteratorMock)
                stream.consume(skippedBefore)
                iteratorMock.__next__.reset_mock()

                # act1
                with self.assertRaises(IndexError):
                    stream[itemIndex]

                # assert1
                # It iterate once on the empty source so the source can raise a StopIteration. After that, it should not iterate anymore on the source since we know it's empty.
                self.assertEqual(iteratorMock.__next__.call_count, 1)

                # arrange2
                iteratorMock.__next__.reset_mock()

                # act2
                with self.assertRaises(IndexError):
                    stream[itemIndex]

                # assert2
                self.assertEqual(iteratorMock.__next__.call_count, 0)

    def test_getItem_withIndexOnEmptySource_finalStateIsValid(self):
        for (index, (skippedBefore, stateTesterGenerator, itemIndex)) in enumerate(itertools.product(
            [0, 2],                     # skippedBefore
            StateTesterGenerators(),    # stateTesterGenerator
            [1, 0, -1],                    # itemIndex
        )):
            stateTester = stateTesterGenerator()
            # remove nullcontext() for more details...but pay a dear execution time price in VSCode
            with nullcontext() or self.subTest(f"index: {index:04d} skippedBefore: {skippedBefore} stateTester: {stateTester} itemIndex: {itemIndex}"):
                # arrange
                stateTester.setup(
                    testCase=self,
                    initialDataSize=skippedBefore,
                    skippedBefore=skippedBefore,
                )
                stream = stateTester.arrangeStep()

                # act
                with self.assertRaises(IndexError):
                    stream[itemIndex]

                # assert
                stateTester.assertStep()

    def test_getItem_withIndexWhenOutOfBound_raisesIndexError(self):
        iterableSize = 5
        for index, (skippedBefore, cachedBefore, iterableGenerator, outOfBoundIndex) in enumerate(itertools.product(
            [0, 2],                 # skippedBefore
            [0, 2],                 # cachedBefore
            iterableGenerators(),   # iterableGenerator
            [-10, -6, 5, 6, 10],    # outOfBoundIndex
        )):
            iterable = iterableGenerator(size=skippedBefore + iterableSize)
            # remove nullcontext() for more details...but pay a dear execution time price in VSCode
            with nullcontext() or self.subTest(f"index: {index:04d} skippedBefore: {skippedBefore} cachedBefore: {cachedBefore} iterable: {iterable} outOfBoundIndex: {outOfBoundIndex}"):
                # arrange
                stream = StreamSequence(iterable)
                stream.consume(skippedBefore)
                preloadData(stream=stream, preload=cachedBefore)

                # assert
                with self.assertRaises(IndexError):
                    # act
                    stream[outOfBoundIndex]

    def test_getItem_withIndexWhenOutOfBound_iterateAsMuchAsPossible(self):

        iterableSize = 5
        for index, (skippedBefore, cachedBefore, outOfBoundIndex) in enumerate(itertools.product(
            [0, 2],                 # skippedBefore
            [0, 2],                 # cachedBefore
            [-10, -6, 5, 6, 10],    # outOfBoundIndex
        )):
            # remove nullcontext() for more details...but pay a dear execution time price in VSCode
            with nullcontext() or self.subTest(f"index: {index:04d} skippedBefore: {skippedBefore} cachedBefore: {cachedBefore} outOfBoundIndex: {outOfBoundIndex}"):
                # arrange1
                iteratorMock = build_IteratorMock(range(iterableSize + skippedBefore))
                stream = StreamSequence(iteratorMock)
                stream.consume(skippedBefore)
                preloadData(stream=stream, preload=cachedBefore)
                iteratorMock.__next__.reset_mock()

                # act1
                with self.assertRaises(IndexError):
                    stream[outOfBoundIndex]

                # assert1
                self.assertEqual(iteratorMock.__next__.call_count, iterableSize + 1 - cachedBefore)

                # arrange2
                iteratorMock.__next__.reset_mock()

                # act2
                with self.assertRaises(IndexError):
                    stream[outOfBoundIndex]

                # assert2
                # TODO: Should be zero with a better implementation
                self.assertEqual(iteratorMock.__next__.call_count, 0)

    def test_getItem_withIndexWhenOutOfBound_finalStateIsValid(self):
        iterableSize = 5
        for index, (skippedBefore, cachedBefore, stateTesterGenerator, outOfBoundIndex) in enumerate(itertools.product(
            [0, 2],                     # skippedBefore
            [0, 2],                     # cachedBefore
            StateTesterGenerators(),    # stateTesterGenerator
            [-10, -6, 5, 6, 10],        # outOfBoundIndex
        )):
            stateTester = stateTesterGenerator()
            # remove nullcontext() for more details...but pay a dear execution time price in VSCode
            with nullcontext() or self.subTest(f"index: {index:04d} skippedBefore: {skippedBefore} cachedBefore: {cachedBefore} stateTester: {stateTester} outOfBoundIndex: {outOfBoundIndex}"):
                # arrange
                stateTester.setup(
                    testCase=self,
                    initialDataSize=skippedBefore + iterableSize,
                    skippedBefore=skippedBefore,
                    cachedBefore=cachedBefore,
                    cachedAfter=iterableSize
                )
                stream = stateTester.arrangeStep()

                # act
                with self.assertRaises(IndexError):
                    stream[outOfBoundIndex]

                # assert
                stateTester.assertStep()

    def test_getItem_withIndex_returnsValue(self):
        iterableSize = 5
        for index, (skippedBefore, cachedBefore, iterableGenerator, validIndex) in enumerate(itertools.product(
            [0, 2],                 # skippedBefore
            [0, 3],                 # cachedBefore
            iterableGenerators(),   # iterableGenerator
            [-5, -1, 0, 2, 4],      # validIndex
        )):
            iterable = iterableGenerator(size=skippedBefore + iterableSize)
            # remove nullcontext() for more details...but pay a dear execution time price in VSCode
            with nullcontext() or self.subTest(f"index: {index:04d} skippedBefore: {skippedBefore} cachedBefore: {cachedBefore} iterable: {iterable} validIndex: {validIndex}"):

                # arrange
                stream = StreamSequence(iterable)
                stream.consume(skippedBefore)
                preloadData(stream=stream, preload=cachedBefore)

                # act
                value = stream[validIndex]

                # assert
                self.assertEqual(list(range(skippedBefore, skippedBefore + iterableSize))[validIndex], value)

    def test_getItem_withIndex_iterateOnSource(self):
        iterableSize = 5
        for index, (skippedBefore, cachedBefore, validIndex) in enumerate(itertools.product(
            [0, 2],                     # skippedBefore
            [0, 3],                     # cachedBefore
            [-5, -1, 0, 2, 4],          # validIndex
        )):
            # remove nullcontext() for more details...but pay a dear execution time price in VSCode
            with nullcontext() or self.subTest(f"index: {index:04d} skippedBefore: {skippedBefore} cachedBefore: {cachedBefore} validIndex: {validIndex}"):
                # arrange
                iteratorMock = build_IteratorMock(range(iterableSize + skippedBefore))
                stream = StreamSequence(iteratorMock)
                stream.consume(skippedBefore)
                preloadData(stream=stream, preload=cachedBefore)
                iteratorMock.__next__.reset_mock()

                # act
                stream[validIndex]

                # assert
                self.assertEqual(iteratorMock.__next__.call_count, max(0, validIndex + 1 - cachedBefore) if validIndex >= 0 else (iterableSize + 1 - cachedBefore))

    def test_getItem_withIndex_finalStateIsValid(self):
        iterableSize = 5
        for index, (skippedBefore, cachedBefore, stateTesterGenerator, validIndex) in enumerate(itertools.product(
            [0, 2],                     # skippedBefore
            [0, 3],                     # cachedBefore
            StateTesterGenerators(),    # stateTesterGenerator
            [-5, -1, 0, 2, 4],          # validIndex
        )):
            stateTester = stateTesterGenerator()
            # remove nullcontext() for more details...but pay a dear execution time price in VSCode
            with nullcontext() or self.subTest(f"index: {index:04d} skippedBefore: {skippedBefore} cachedBefore: {cachedBefore} stateTester: {stateTester} validIndex: {validIndex}"):

                # arrange
                stateTester.setup(
                    testCase=self,
                    initialDataSize=skippedBefore + iterableSize,
                    skippedBefore=skippedBefore,
                    cachedBefore=cachedBefore,
                    cachedAfter=max(cachedBefore, validIndex + 1) if validIndex >= 0 else iterableSize
                )
                stream = stateTester.arrangeStep()

                # act
                stream[validIndex]

                # assert
                stateTester.assertStep()

    # ==== take / consume (advance the visible front) ===

    def test_advance_whenAdvancingNElements_iterateAccordingly(self):
        for index, (advanceOp, skippedBefore, cachedBefore, holdLiveIterator) in enumerate(itertools.product(
            advanceOperations(),    # advanceOp
            [0, 2],                 # skippedBefore
            [0, 1, 2, 3],           # cachedBefore
            [False, True],          # holdLiveIterator: forces the slow path when True
        )):
            # remove nullcontext() for more details...but pay a dear execution time price in VSCode
            with nullcontext() or self.subTest(f"index: {index:04d} op: {advanceOp.name} skippedBefore: {skippedBefore} cachedBefore: {cachedBefore} holdLiveIterator: {holdLiveIterator}"):  # noqa: E501
                # arrange
                iteratorMock = build_IteratorMock(range(5 + skippedBefore))
                stream = StreamSequence(iteratorMock)
                stream.consume(skippedBefore)
                preloadData(stream=stream, preload=cachedBefore)
                # A held, unadvanced sub-iterator keeps _liveSubIterators non-empty,
                # routing the advance through the slow path. It pins the prefix but
                # changes neither the new source pulls nor the returned values.
                liveIterator = iter(stream) if holdLiveIterator else None  # noqa: F841
                iteratorMock.__next__.reset_mock()

                # act
                advanceOp.apply(stream, 2)

                # assert
                self.assertEqual(iteratorMock.__next__.call_count, max(0, 2 - cachedBefore))

    def test_advance_whenAdvancingNElements_returnsAdvancedElements(self):
        for index, (advanceOp, skippedBefore, cachedBefore, iterableGenerator, holdLiveIterator) in enumerate(itertools.product(
            advanceOperations(),    # advanceOp
            [0, 2],                 # skippedBefore
            [0, 1, 2, 3],           # cachedBefore
            iterableGenerators(),   # iterableGenerator
            [False, True],          # holdLiveIterator: forces the slow path when True
        )):
            iterable = iterableGenerator(size=skippedBefore + 5)
            # remove nullcontext() for more details...but pay a dear execution time price in VSCode
            with nullcontext() or self.subTest(f"index: {index:04d} op: {advanceOp.name} skippedBefore: {skippedBefore} cachedBefore: {cachedBefore} iterable: {iterable} holdLiveIterator: {holdLiveIterator}"):  # noqa: E501
                # arrange
                stream = StreamSequence(iterable)
                stream.consume(skippedBefore)
                preloadData(stream=stream, preload=cachedBefore)
                # See note in test_advance_whenAdvancingNElements_iterateAccordingly.
                liveIterator = iter(stream) if holdLiveIterator else None  # noqa: F841

                # act
                result = advanceOp.apply(stream, 3)

                # assert
                self.assertEqual(result, advanceOp.expectedReturn(list(range(skippedBefore, 3 + skippedBefore))))

    def test_advance_whenAdvancingNElements_finalStateIsValid(self):
        iterableSize = 5
        for index, (advanceOp, skippedBefore, cachedBefore, stateTesterGenerator) in enumerate(itertools.product(
            advanceOperations(),        # advanceOp
            [0, 2],                     # skippedBefore
            [0, 1, 2, 3],               # cachedBefore
            StateTesterGenerators(),    # stateTesterGenerator
        )):
            stateTester = stateTesterGenerator()
            # remove nullcontext() for more details...but pay a dear execution time price in VSCode
            with nullcontext() or self.subTest(f"index: {index:04d} op: {advanceOp.name} skippedBefore: {skippedBefore} cachedBefore: {cachedBefore} stateTester: {stateTester}"):  # noqa: E501

                # arrange
                stateTester.setup(
                    testCase=self,
                    initialDataSize=skippedBefore + iterableSize,
                    skippedBefore=skippedBefore,
                    skippedAfter=skippedBefore + 2,
                    cachedBefore=cachedBefore,
                    cachedAfter=max(cachedBefore - 2, 0)
                )
                stream = stateTester.arrangeStep()

                # act
                advanceOp.apply(stream, 2)

                # assert
                stateTester.assertStep()

    def test_advance_whenAdvancing0OrLessElements_doesNotIterateOnSource(self):
        for index, (advanceOp, skippedBefore, cachedBefore, advancing, holdLiveIterator) in enumerate(itertools.product(
            advanceOperations(),    # advanceOp
            [0, 2],                 # skippedBefore
            [0, 1, 2, 3],           # cachedBefore
            [0, -2],                # advancing
            [False, True],          # holdLiveIterator: forces the slow path when True
        )):
            # remove nullcontext() for more details...but pay a dear execution time price in VSCode
            with nullcontext() or self.subTest(f"index: {index:04d} op: {advanceOp.name} skippedBefore: {skippedBefore} cachedBefore: {cachedBefore} advancing: {advancing} holdLiveIterator: {holdLiveIterator}"):  # noqa: E501

                # arrange
                iteratorMock = build_IteratorMock(range(5))
                stream = StreamSequence(iteratorMock)
                stream.consume(skippedBefore)
                preloadData(stream=stream, preload=cachedBefore)
                # A held, unadvanced sub-iterator keeps _liveSubIterators non-empty,
                # routing the advance through the slow path. It pins the prefix but
                # changes neither the new source pulls nor the returned values.
                liveIterator = iter(stream) if holdLiveIterator else None  # noqa: F841
                iteratorMock.__next__.reset_mock()

                # act
                advanceOp.apply(stream, advancing)

                # assert
                self.assertEqual(iteratorMock.__next__.call_count, 0)

    def test_advance_whenAdvancing0OrLessElements_returnsEmptyResult(self):
        for index, (advanceOp, skippedBefore, cachedBefore, advancing, iterableGenerator, holdLiveIterator) in enumerate(itertools.product(
            advanceOperations(),    # advanceOp
            [0, 2],                 # skippedBefore
            [0, 1, 2, 3],           # cachedBefore
            [0, -2],                # advancing
            iterableGenerators(),   # iterableGenerator
            [False, True],          # holdLiveIterator: forces the slow path when True
        )):
            iterable = iterableGenerator(size=skippedBefore + 5)
            # remove nullcontext() for more details...but pay a dear execution time price in VSCode
            with nullcontext() or self.subTest(f"index: {index:04d} op: {advanceOp.name} skippedBefore: {skippedBefore} cachedBefore: {cachedBefore} advancing: {advancing} iterable: {iterable} holdLiveIterator: {holdLiveIterator}"):  # noqa: E501

                # arrange
                stream = StreamSequence(iterable)
                stream.consume(n=skippedBefore)
                preloadData(stream=stream, preload=cachedBefore)
                # See note in test_advance_whenAdvancing0OrLessElements_doesNotIterateOnSource.
                liveIterator = iter(stream) if holdLiveIterator else None  # noqa: F841

                # act
                result = advanceOp.apply(stream, advancing)

                # assert
                self.assertEqual(result, advanceOp.expectedReturn([]))

    def test_advance_whenAdvancing0OrLessElements_finalStateIsValid(self):
        for index, (advanceOp, skippedBefore, cachedBefore, advancing, stateTesterGenerator) in enumerate(itertools.product(
            advanceOperations(),        # advanceOp
            [0, 2],                     # skippedBefore
            [0, 1, 2, 3],               # cachedBefore
            [0, -2],                    # advancing
            StateTesterGenerators(),    # stateTesterGenerator
        )):
            stateTester = stateTesterGenerator()
            # remove nullcontext() for more details...but pay a dear execution time price in VSCode
            with nullcontext() or self.subTest(f"index: {index:04d} op: {advanceOp.name} skippedBefore: {skippedBefore} cachedBefore: {cachedBefore} advancing: {advancing} stateTester: {stateTester}"):  # noqa: E501

                # arrange
                stateTester.setup(
                    testCase=self,
                    initialDataSize=skippedBefore + 5,
                    skippedBefore=skippedBefore,
                    cachedBefore=cachedBefore,
                )
                stream = stateTester.arrangeStep()

                # act
                advanceOp.apply(stream, advancing)

                # assert
                stateTester.assertStep()

    def test_advance_whenAdvancingNoneOrMoreElementsThanAvailable_iterateOnAvailableElements(self):
        for index, (advanceOp, skippedBefore, cachedBefore, initialSize, advancing, holdLiveIterator) in enumerate(itertools.product(
            advanceOperations(),    # advanceOp
            [0, 2],                 # skippedBefore
            [0, 2],                 # cachedBefore
            [0, 5],                 # initialSize
            [10, None],             # advancing
            [False, True],          # holdLiveIterator: forces the slow path when True
        )):
            # remove nullcontext() for more details...but pay a dear execution time price in VSCode
            with nullcontext() or self.subTest(f"index: {index:04d} op: {advanceOp.name} skippedBefore: {skippedBefore} cachedBefore: {cachedBefore} initialSize: {initialSize} advancing: {advancing} holdLiveIterator: {holdLiveIterator}"):  # noqa: E501

                # arrange
                iteratorMock = build_IteratorMock(range(initialSize + skippedBefore))
                stream = StreamSequence(iteratorMock)
                stream.consume(n=skippedBefore)
                preloadData(stream=stream, preload=cachedBefore)
                # A held, unadvanced sub-iterator keeps _liveSubIterators non-empty,
                # routing the advance through the slow path. It pins the prefix but
                # changes neither the new source pulls nor the returned values.
                liveIterator = iter(stream) if holdLiveIterator else None  # noqa: F841
                iteratorMock.__next__.reset_mock()

                # act
                advanceOp.apply(stream, advancing)

                # assert
                self.assertEqual(iteratorMock.__next__.call_count, max(0, initialSize - cachedBefore) + (1 if cachedBefore <= initialSize else 0))  # number of elements + StopIteration  # noqa: E501

    def test_advance_whenAdvancingNoneOrMoreElementsThanAvailable_returnsWhatCanBeAdvanced(self):
        for index, (advanceOp, skippedBefore, cachedBefore, initialSize, iterableGenerator, advancing, holdLiveIterator) in enumerate(itertools.product(
            advanceOperations(),    # advanceOp
            [0, 2],                 # skippedBefore
            [0, 2],                 # cachedBefore
            [0, 5],                 # initialSize
            iterableGenerators(),   # iterableGenerator
            [10, None],             # advancing
            [False, True],          # holdLiveIterator: forces the slow path when True
        )):
            iterable = iterableGenerator(size=skippedBefore + initialSize)
            # remove nullcontext() for more details...but pay a dear execution time price in VSCode
            with nullcontext() or self.subTest(f"index: {index:04d} op: {advanceOp.name} skippedBefore: {skippedBefore} cachedBefore: {cachedBefore} initialSize: {initialSize} iterable: {iterable} advancing: {advancing} holdLiveIterator: {holdLiveIterator}"):  # noqa: E501

                # arrange
                stream = StreamSequence(iterable)
                stream.consume(n=skippedBefore)
                preloadData(stream=stream, preload=cachedBefore)
                # See note in the *_iterateOnAvailableElements counterpart.
                liveIterator = iter(stream) if holdLiveIterator else None  # noqa: F841

                # act
                result = advanceOp.apply(stream, advancing)

                # assert
                self.assertEqual(result, advanceOp.expectedReturn(list(range(skippedBefore, skippedBefore + initialSize))))

    def test_advance_whenAdvancingNoneOrMoreElementsThanAvailable_finalStateIsValid(self):
        for index, (advanceOp, skippedBefore, cachedBefore, initialSize, stateTesterGenerator, advancing) in enumerate(itertools.product(
            advanceOperations(),        # advanceOp
            [0, 2],                     # skippedBefore
            [0, 2],                     # cachedBefore
            [0, 5],                     # initialSize
            StateTesterGenerators(),    # stateTesterGenerator
            [10, None],                 # advancing
        )):
            stateTester = stateTesterGenerator()
            # since we're also testing empty source...not all configurations are valid
            cachedBefore = min(cachedBefore, initialSize)
            # remove nullcontext() for more details...but pay a dear execution time price in VSCode
            with nullcontext() or self.subTest(f"index: {index:04d} op: {advanceOp.name} skippedBefore: {skippedBefore} cachedBefore: {cachedBefore} initialSize: {initialSize} stateTester: {stateTester} advancing: {advancing}"):  # noqa: E501

                # arrange
                stateTester.setup(
                    testCase=self,
                    initialDataSize=skippedBefore + initialSize,
                    skippedBefore=skippedBefore,
                    skippedAfter=skippedBefore + initialSize,
                    cachedBefore=cachedBefore,
                    cachedAfter=0
                )
                stream = stateTester.arrangeStep()

                # act
                advanceOp.apply(stream, advancing)

                # assert
                stateTester.assertStep()

    # ==== getItem with a slice ===

    def test_getItem_withSliceWhenAccessingData_returnsExpectedValue(self):
        for (index, (iterableSize, cachedBefore, skippedBefore, sliceTestCase, iterableGenerator)) in enumerate(itertools.product(
            [0, 10],                # iterableSize
            [0, 3, 10],             # cachedBefore
            [0, 2],                 # skippedBefore
            sliceTestCases(),       # sliceTestCase
            iterableGenerators(),  # iterableGenerator
        )):
            iterable = iterableGenerator(size=iterableSize + skippedBefore)
            # remove nullcontext() for more details...but pay a dear execution time price in VSCode
            with nullcontext() or self.subTest(f"index: {index:04d} iterableSize: {iterableSize} cachedBefore: {cachedBefore} skippedBefore: {skippedBefore} sliceTestCase: {sliceTestCase} iterable: {iterable}"):  # noqa: E501

                # arrange1
                stream = StreamSequence(iterable)
                stream.consume(skippedBefore)                            # skippedBefore
                preloadData(stream=stream, preload=cachedBefore)    # cachedBefore

                # act1
                aSlice = stream[sliceTestCase]
                valuesOnce = list(aSlice)

                # assert1
                self.assertEqual(valuesOnce, list(range(skippedBefore, iterableSize + skippedBefore))[sliceTestCase])

                # act2
                valuesTwice = list(aSlice)

                # assert2
                self.assertEqual(valuesOnce, valuesTwice)

    def test_getItem_withSliceWhenAccessingData_iterateOnSource(self):
        for (index, (iterableSize, cachedBefore, skippedBefore, sliceTestCase)) in enumerate(itertools.product(
            [0, 10],            # iterableSize
            [0, 3],             # cachedBefore
            [0, 2],             # skippedBefore
            sliceTestCases(),   # sliceTestCase
        )):
            # remove nullcontext() for more details...but pay a dear execution time price in VSCode
            with nullcontext() or self.subTest(f"index: {index:04d} iterableSize: {iterableSize} cachedBefore: {cachedBefore} skippedBefore: {skippedBefore} sliceTestCase: {sliceTestCase}"):

                # arrange1
                ish = IteratorSliceHelper.FROM(iterableSize=iterableSize)
                list(ish[sliceTestCase])
                expectedNextCallsCount = ish.nextCallsCount

                iteratorMock = build_IteratorMock(range(iterableSize + skippedBefore))
                stream = StreamSequence(iteratorMock)
                stream.consume(skippedBefore)                            # skippedBefore
                preloadData(stream=stream, preload=cachedBefore)    # cachedBefore
                iteratorMock.__next__.reset_mock()

                # act1
                aSlice = stream[sliceTestCase]
                list(aSlice)

                # assert1
                self.assertEqual(iteratorMock.__next__.call_count, max(expectedNextCallsCount - cachedBefore, 0))

                # arrange2
                iteratorMock.__next__.reset_mock()

                # act2
                list(aSlice)

                # assert2
                self.assertEqual(iteratorMock.__next__.call_count, 0)

    def test_getItem_withSliceWhenAccessingData_finalStateIsValid(self):
        for (index, (iterableSize, cachedBefore, skippedBefore, sliceTestCase, stateTesterGenerator)) in enumerate(itertools.product(
            [0, 10],                    # iterableSize
            [0, 3],                     # cachedBefore
            [0, 2],                     # skippedBefore
            sliceTestCases(),           # sliceTestCase
            StateTesterGenerators(),    # stateTester
        )):
            stateTester = stateTesterGenerator()
            # remove nullcontext() for more details...but pay a dear execution time price in VSCode
            with nullcontext() or self.subTest(f"index: {index:04d} iterableSize: {iterableSize} cachedBefore: {cachedBefore} skippedBefore: {skippedBefore} sliceTestCase: {sliceTestCase} stateTester: {stateTester}"):  # noqa: E501

                # arrange
                ish = IteratorSliceHelper.FROM(iterableSize=iterableSize)
                list(ish[sliceTestCase])
                expectedNextCallsCount = ish.nextCallsCount

                cachedBefore = min(cachedBefore, iterableSize)  # cachedBefore cannot be more than the iterable size

                stateTester.setup(
                    testCase=self,
                    initialDataSize=iterableSize + skippedBefore,
                    cachedBefore=cachedBefore,
                    skippedBefore=skippedBefore,
                    cachedAfter=max(cachedBefore, min(expectedNextCallsCount, iterableSize)),
                )
                stream = stateTester.arrangeStep()

                # act
                list(stream[sliceTestCase])

                # assert
                stateTester.assertStep()

    def test_getItem_withSliceWhenNotAccessingData_doesNotIterateOnSource(self):
        for (index, (iterableSize, cachedBefore, skippedBefore, sliceTestCase)) in enumerate(itertools.product(
            [0, 10],            # iterableSize
            [0, 3],             # cachedBefore
            [0, 2],             # skippedBefore
            sliceTestCases(),   # sliceTestCase
        )):
            # remove nullcontext() for more details...but pay a dear execution time price in VSCode
            with nullcontext() or self.subTest(f"index: {index:04d} iterableSize: {iterableSize} cachedBefore: {cachedBefore} skippedBefore: {skippedBefore} sliceTestCase: {sliceTestCase}"):

                # arrange
                iteratorMock = build_IteratorMock(range(iterableSize + skippedBefore))
                stream = StreamSequence(iteratorMock)
                stream.consume(skippedBefore)                            # skippedBefore
                preloadData(stream=stream, preload=cachedBefore)    # cachedBefore
                iteratorMock.__next__.reset_mock()

                # act
                stream[sliceTestCase]

                # assert
                self.assertEqual(iteratorMock.__next__.call_count, 0)

    def test_getItem_withSliceWhenNotAccessingData_finalStateIsValid(self):
        for (index, (iterableSize, cachedBefore, skippedBefore, sliceTestCase, stateTesterGenerator)) in enumerate(itertools.product(
            [0, 10],                    # iterableSize
            [0, 3],                     # cachedBefore
            [0, 2],                     # skippedBefore
            sliceTestCases(),           # sliceTestCase
            StateTesterGenerators(),    # stateTester
        )):
            stateTester = stateTesterGenerator()
            # remove nullcontext() for more details...but pay a dear execution time price in VSCode
            with nullcontext() or self.subTest(f"index: {index:04d} iterableSize: {iterableSize} cachedBefore: {cachedBefore} skippedBefore: {skippedBefore} sliceTestCase: {sliceTestCase} stateTester: {stateTester}"):  # noqa: E501

                cachedBefore = min(cachedBefore, iterableSize)  # cachedBefore cannot be more than the iterable size

                # arrange
                stateTester.setup(
                    testCase=self,
                    initialDataSize=iterableSize + skippedBefore,
                    cachedBefore=cachedBefore,
                    skippedBefore=skippedBefore,
                )
                stream = stateTester.arrangeStep()

                # act
                stream[sliceTestCase]

                # assert
                stateTester.assertStep()

    # ==== getItem with a slice from a slice ====

    def test_getItem_withSliceFromSliceWhenAccessingData_returnsExpectedValue(self):
        for (index, (iterableSize, cachedBefore, skippedBefore, sliceTestCase1, sliceTestCase2)) in enumerate(itertools.product(
            [0, 10],             # iterableSize
            [0, 3, 10],         # cachedBefore
            [0, 2],             # skippedBefore
            sliceTestCasesLight(),   # sliceTestCase1
            sliceTestCasesLight(),   # sliceTestCase2
        )):
            # remove nullcontext() for more details...but pay a dear execution time price in VSCode
            with nullcontext() or self.subTest(f"index: {index:04d} iterableSize: {iterableSize} cachedBefore: {cachedBefore} skippedBefore: {skippedBefore} sliceTestCase1: {sliceTestCase1} sliceTestCase2: {sliceTestCase2}"):  # noqa: E501

                # arrange
                stream = StreamSequence(range(iterableSize + skippedBefore))
                stream.consume(skippedBefore)                            # skippedBefore
                preloadData(stream=stream, preload=cachedBefore)    # cachedBefore

                # act1
                values1 = list(stream[sliceTestCase1][sliceTestCase2])

                # assert1
                self.assertEqual(values1, list(range(skippedBefore, iterableSize + skippedBefore))[sliceTestCase1][sliceTestCase2])

                # act2 - same operation but in two steps. We first consume/retrieve all the data for sliceTestCase1
                aSlice = stream[sliceTestCase1]
                list(aSlice)
                values2 = list(aSlice[sliceTestCase2])

                # assert2
                self.assertEqual(values2, values1)

    def test_getItem_withSliceFromSliceWhenAccessingData_iterateOnSource(self):
        for (index, (iterableSize, cachedBefore, skippedBefore, sliceTestCase1, sliceTestCase2)) in enumerate(itertools.product(
            [0, 10],             # iterableSize
            [0, 3, 10],         # cachedBefore
            [0, 2],             # skippedBefore
            sliceTestCasesLight(),   # sliceTestCase1
            sliceTestCasesLight(),   # sliceTestCase2
        )):
            # remove nullcontext() for more details...but pay a dear execution time price in VSCode
            with nullcontext() or self.subTest(f"index: {index:04d} iterableSize: {iterableSize} cachedBefore: {cachedBefore} skippedBefore: {skippedBefore} sliceTestCase1: {sliceTestCase1} sliceTestCase2: {sliceTestCase2}"):  # noqa: E501

                # arrange1
                ish = IteratorSliceHelper.FROM(iterableSize=iterableSize)
                list(ish[sliceTestCase1][sliceTestCase2])
                expectedNextCallsCount = ish.nextCallsCount

                iteratorMock = build_IteratorMock(range(iterableSize + skippedBefore))
                stream = StreamSequence(iteratorMock)
                stream.consume(skippedBefore)                            # skippedBefore
                preloadData(stream=stream, preload=cachedBefore)    # cachedBefore
                iteratorMock.__next__.reset_mock()

                # act1
                list(stream[sliceTestCase1][sliceTestCase2])

                # assert1
                self.assertEqual(iteratorMock.__next__.call_count, max(expectedNextCallsCount - cachedBefore, 0))

                # arrange2 - same operation but in two steps. We first consume/retrieve all the data for sliceTestCase1
                iteratorMock = build_IteratorMock(range(iterableSize + skippedBefore))
                stream = StreamSequence(iteratorMock)
                stream.consume(skippedBefore)                            # skippedBefore
                preloadData(stream=stream, preload=cachedBefore)    # cachedBefore
                aSlice = stream[sliceTestCase1]
                list(aSlice)
                iteratorMock.__next__.reset_mock()

                # act2
                list(aSlice[sliceTestCase2])

                # assert2
                # once the first level slice has been fully consumed, by design, no access to the initial iterator will be performed.
                # we use an intermediary "generator" that wraps the original sliced stream and therefore shield subsequent slices from ever accessing the original iterator.
                self.assertEqual(iteratorMock.__next__.call_count, 0)

    def test_getItem_withSliceFromSliceWhenAccessingData_finalStateIsValid(self):
        for (index, (iterableSize, cachedBefore, skippedBefore, sliceTestCase1, sliceTestCase2, stateTesterGenerator)) in enumerate(itertools.product(
            [0, 10],            # iterableSize
            [0, 3, 10],         # cachedBefore
            [0, 2],             # skippedBefore
            sliceTestCasesLight(),   # sliceTestCase1
            sliceTestCasesLight(),   # sliceTestCase2
            StateTesterGenerators(light=True),  # stateTester
        )):
            stateTester = stateTesterGenerator()
            # remove nullcontext() for more details...but pay a dear execution time price in VSCode
            with nullcontext() or self.subTest(f"index: {index:04d} iterableSize: {iterableSize} cachedBefore: {cachedBefore} skippedBefore: {skippedBefore} sliceTestCase1: {sliceTestCase1} sliceTestCase2: {sliceTestCase2} stateTester: {stateTester}"):  # noqa: E501

                # arrange1
                ish = IteratorSliceHelper.FROM(iterableSize=iterableSize)
                list(ish[sliceTestCase1][sliceTestCase2])
                expectedNextCallsCount = ish.nextCallsCount

                cachedBefore = min(cachedBefore, iterableSize)  # cachedBefore cannot be more than the iterable size

                stateTester.setup(
                    testCase=self,
                    initialDataSize=iterableSize + skippedBefore,
                    cachedBefore=cachedBefore,
                    skippedBefore=skippedBefore,
                    cachedAfter=max(min(expectedNextCallsCount, iterableSize), cachedBefore),
                )
                stream = stateTester.arrangeStep()

                # act1
                list(stream[sliceTestCase1][sliceTestCase2])

                # assert1
                stateTester.assertStep()

                # arrange2 - same operation but in two steps. We first consume/retrieve all the data for sliceTestCase1
                ish = IteratorSliceHelper.FROM(iterableSize=iterableSize)
                list(ish[sliceTestCase1])
                expectedNextCallsCount = ish.nextCallsCount

                stateTester.setup(
                    testCase=self,
                    initialDataSize=iterableSize + skippedBefore,
                    cachedBefore=cachedBefore,
                    skippedBefore=skippedBefore,
                    cachedAfter=max(min(expectedNextCallsCount, iterableSize), cachedBefore),
                )
                stream = stateTester.arrangeStep()
                aSlice = stream[sliceTestCase1]
                list(aSlice)

                # act2
                list(aSlice[sliceTestCase2])

                # assert2
                stateTester.assertStep()

    def test_getItem_withSliceFromSliceWhenNotAccessingData_doesNotIterateOnSource(self):
        for (index, (iterableSize, cachedBefore, skippedBefore, sliceTestCase1, sliceTestCase2)) in enumerate(itertools.product(
            [0, 10],            # iterableSize
            [0, 3, 10],         # cachedBefore
            [0, 2],             # skippedBefore
            sliceTestCasesLight(),   # sliceTestCase1
            sliceTestCasesLight(),   # sliceTestCase2
        )):
            # remove nullcontext() for more details...but pay a dear execution time price in VSCode
            with nullcontext() or self.subTest(f"index: {index:04d} iterableSize: {iterableSize} cachedBefore: {cachedBefore} skippedBefore: {skippedBefore} sliceTestCase1: {sliceTestCase1} sliceTestCase2: {sliceTestCase2}"):  # noqa: E501

                # arrange1
                iteratorMock = build_IteratorMock(range(iterableSize + skippedBefore))
                stream = StreamSequence(iteratorMock)
                stream.consume(skippedBefore)                            # skippedBefore
                preloadData(stream=stream, preload=cachedBefore)    # cachedBefore
                iteratorMock.__next__.reset_mock()

                # act1
                stream[sliceTestCase1][sliceTestCase2]

                # assert1
                self.assertEqual(iteratorMock.__next__.call_count, 0)

    def test_getItem_withSliceFromSliceWhenNotAccessingData_finalStateIsValid(self):
        for (index, (iterableSize, cachedBefore, skippedBefore, sliceTestCase1, sliceTestCase2, stateTesterGenerator)) in enumerate(itertools.product(
            [0, 10],            # iterableSize
            [0, 3, 10],         # cachedBefore
            [0, 2],             # skippedBefore
            sliceTestCasesLight(),   # sliceTestCase1
            sliceTestCasesLight(),   # sliceTestCase2
            StateTesterGenerators(light=True),  # stateTester
        )):
            stateTester = stateTesterGenerator()
            # remove nullcontext() for more details...but pay a dear execution time price in VSCode
            with nullcontext() or self.subTest(f"index: {index:04d} iterableSize: {iterableSize} cachedBefore: {cachedBefore} skippedBefore: {skippedBefore} sliceTestCase1: {sliceTestCase1} sliceTestCase2: {sliceTestCase2} stateTester: {stateTester}"):  # noqa: E501

                # arrange1
                cachedBefore = min(cachedBefore, iterableSize)  # cachedBefore cannot be more than the iterable size

                stateTester.setup(
                    testCase=self,
                    initialDataSize=iterableSize + skippedBefore,
                    cachedBefore=cachedBefore,
                    skippedBefore=skippedBefore,
                )
                stream = stateTester.arrangeStep()

                # act1
                stream[sliceTestCase1][sliceTestCase2]

                # assert1
                stateTester.assertStep()

    # ================================================================================================

    def test_getItem_withValidIndexFromSlice_returnsExpectedValue(self):
        iterableSize = 10
        for (index, (cachedBefore, skippedBefore, testCase)) in enumerate(itertools.product(
            [0, 3, 10],                         # cachedBefore
            [0, 2],                             # skippedBefore
            inRangeValueFromSliceTestCases(),   # testCaseGenerator
        )):
            # remove nullcontext() for more details...but pay a dear execution time price in VSCode
            with nullcontext() or self.subTest(f"index: {index:04d} cachedBefore: {cachedBefore} skippedBefore: {skippedBefore} testCaseGenerator: {testCase}"):

                # arrange1
                stream = StreamSequence(range(iterableSize + skippedBefore))
                stream.consume(skippedBefore)                            # skippedBefore
                preloadData(stream=stream, preload=cachedBefore)    # cachedBefore

                # act1
                value = testCase.testCase(stream)

                # assert1
                self.assertEqual(value, testCase.testCase(range(skippedBefore, skippedBefore + iterableSize)))

                # arrange2
                stream = StreamSequence(range(iterableSize + skippedBefore))
                stream.consume(skippedBefore)                            # skippedBefore
                preloadData(stream=stream, preload=cachedBefore)    # cachedBefore

                # act2
                value = testCase.testCase(stream[0:None])

                # assert2
                self.assertEqual(value, testCase.testCase(range(skippedBefore, skippedBefore + iterableSize)))

    def test_getItem_withValidIndexFromSlice_iterateOnSource(self):
        iterableSize = 10
        for (index, (cachedBefore, skippedBefore, testCase)) in enumerate(itertools.product(
            [0, 3, 10],                         # cachedBefore
            [0, 2],                             # skippedBefore
            inRangeValueFromSliceTestCases(),   # testCaseGenerator
        )):
            # remove nullcontext() for more details...but pay a dear execution time price in VSCode
            with nullcontext() or self.subTest(f"index: {index:04d} cachedBefore: {cachedBefore} skippedBefore: {skippedBefore} testCaseGenerator: {testCase}"):

                # arrange1
                ish = IteratorSliceHelper.FROM(iterableSize=iterableSize)
                testCase.testCase(ish)
                expectedNextCallsCount = ish.nextCallsCount

                iteratorMock = build_IteratorMock(range(iterableSize + skippedBefore))
                stream = StreamSequence(iteratorMock)
                stream.consume(skippedBefore)                            # skippedBefore
                preloadData(stream=stream, preload=cachedBefore)    # cachedBefore
                iteratorMock.__next__.reset_mock()

                # act1
                testCase.testCase(stream)

                # assert1
                self.assertEqual(iteratorMock.__next__.call_count, max(expectedNextCallsCount - cachedBefore, 0))

                # arrange2
                iteratorMock = build_IteratorMock(range(iterableSize + skippedBefore))
                stream = StreamSequence(iteratorMock)
                stream.consume(skippedBefore)                            # skippedBefore
                preloadData(stream=stream, preload=cachedBefore)    # cachedBefore
                iteratorMock.__next__.reset_mock()

                # act2
                testCase.testCase(stream[0:None])

                # assert2
                self.assertEqual(iteratorMock.__next__.call_count, max(expectedNextCallsCount - cachedBefore, 0))

    def test_getItem_withValidIndexFromSlice_finalStateIsValid(self):
        iterableSize = 10
        for (index, (cachedBefore, skippedBefore, testCase, stateTesterGenerator)) in enumerate(itertools.product(
            [0, 3, 10],                         # cachedBefore
            [0, 2],                             # skippedBefore
            inRangeValueFromSliceTestCases(),   # testCaseGenerator
            StateTesterGenerators(light=True),  # stateTester
        )):
            stateTester = stateTesterGenerator()
            # remove nullcontext() for more details...but pay a dear execution time price in VSCode
            with nullcontext() or self.subTest(f"index: {index:04d} cachedBefore: {cachedBefore} skippedBefore: {skippedBefore} testCaseGenerator: {testCase} stateTester: {stateTester}"):

                # arrange1
                ish = IteratorSliceHelper.FROM(iterableSize=iterableSize)
                testCase.testCase(ish)
                expectedNextCallsCount = ish.nextCallsCount

                stateTester.setup(
                    testCase=self,
                    initialDataSize=iterableSize + skippedBefore,
                    cachedBefore=cachedBefore,
                    skippedBefore=skippedBefore,
                    cachedAfter=max(min(expectedNextCallsCount, iterableSize), cachedBefore),
                )
                stream = stateTester.arrangeStep()

                # act1
                testCase.testCase(stream)

                # assert1
                stateTester.assertStep()

                # arrange2
                stateTester.setup(
                    testCase=self,
                    initialDataSize=iterableSize + skippedBefore,
                    cachedBefore=cachedBefore,
                    skippedBefore=skippedBefore,
                    cachedAfter=max(min(expectedNextCallsCount, iterableSize), cachedBefore),
                )
                stream = stateTester.arrangeStep()

                # act2
                testCase.testCase(stream[0:None])

                # assert2
                stateTester.assertStep()

    def test_getItem_withOutOfRangeIndexFromSlice_returnsExpectedValue(self):
        iterableSize = 10
        for (index, (cachedBefore, skippedBefore, testCase)) in enumerate(itertools.product(
            [0, 3, 10],                             # cachedBefore
            [0, 2],                                 # skippedBefore
            outOfRangeValueFromSliceTestCases(),    # testCaseGenerator
        )):
            # remove nullcontext() for more details...but pay a dear execution time price in VSCode
            with nullcontext() or self.subTest(f"index: {index:04d} cachedBefore: {cachedBefore} skippedBefore: {skippedBefore} testCaseGenerator: {testCase}"):

                # arrange1
                stream = StreamSequence(range(iterableSize + skippedBefore))
                stream.consume(skippedBefore)                            # skippedBefore
                preloadData(stream=stream, preload=cachedBefore)    # cachedBefore

                # assert1
                with self.assertRaises(IndexError):
                    # act1
                    testCase.testCase(stream)

                # sanity check
                with self.assertRaises(IndexError):
                    testCase.testCase(range(10))

                # arrange2
                stream = StreamSequence(range(iterableSize + skippedBefore))
                stream.consume(skippedBefore)                            # skippedBefore
                preloadData(stream=stream, preload=cachedBefore)    # cachedBefore

                # assert2
                with self.assertRaises(IndexError):
                    # act2
                    testCase.testCase(stream[0:None])

                # sanity check
                with self.assertRaises(IndexError):
                    testCase.testCase(range(10))

    def test_getItem_withOutOfRangeIndexFromSlice_iterateOnSource(self):
        iterableSize = 10
        for (index, (cachedBefore, skippedBefore, testCase)) in enumerate(itertools.product(
            [0, 3, 10],                             # cachedBefore
            [0, 2],                                 # skippedBefore
            outOfRangeValueFromSliceTestCases(),    # testCaseGenerator
        )):
            # remove nullcontext() for more details...but pay a dear execution time price in VSCode
            with nullcontext() or self.subTest(f"index: {index:04d} cachedBefore: {cachedBefore} skippedBefore: {skippedBefore} testCaseGenerator: {testCase}"):

                # arrange1
                ish = IteratorSliceHelper.FROM(iterableSize=iterableSize)
                try:
                    testCase.testCase(ish)
                except IndexError:
                    pass
                expectedNextCallsCount = ish.nextCallsCount

                iteratorMock = build_IteratorMock(range(iterableSize + skippedBefore))
                stream = StreamSequence(iteratorMock)
                stream.consume(skippedBefore)                            # skippedBefore
                preloadData(stream=stream, preload=cachedBefore)    # cachedBefore
                iteratorMock.__next__.reset_mock()

                with self.assertRaises(IndexError):
                    # act1
                    testCase.testCase(stream)

                # assert1
                self.assertEqual(iteratorMock.__next__.call_count, max(expectedNextCallsCount - cachedBefore, 0))

                # arrange2
                iteratorMock = build_IteratorMock(range(iterableSize + skippedBefore))
                stream = StreamSequence(iteratorMock)
                stream.consume(skippedBefore)                            # skippedBefore
                preloadData(stream=stream, preload=cachedBefore)    # cachedBefore
                iteratorMock.__next__.reset_mock()

                with self.assertRaises(IndexError):
                    # act2
                    testCase.testCase(stream[0:None])

                # assert2
                self.assertEqual(iteratorMock.__next__.call_count, max(expectedNextCallsCount - cachedBefore, 0))

    def test_getItem_withOutOfRangeIndexFromSlice_finalStateIsValid(self):
        iterableSize = 10
        for (index, (cachedBefore, skippedBefore, testCase, stateTesterGenerator)) in enumerate(itertools.product(
            [0, 3, 10],                             # cachedBefore
            [0, 2],                                 # skippedBefore
            outOfRangeValueFromSliceTestCases(),    # testCaseGenerator
            StateTesterGenerators(light=True),      # stateTester
        )):
            stateTester = stateTesterGenerator()
            # remove nullcontext() for more details...but pay a dear execution time price in VSCode
            with nullcontext() or self.subTest(f"index: {index:04d} cachedBefore: {cachedBefore} skippedBefore: {skippedBefore} testCaseGenerator: {testCase} stateTester: {stateTester}"):

                # arrange1
                ish = IteratorSliceHelper.FROM(iterableSize=iterableSize)
                try:
                    testCase.testCase(ish)
                except IndexError:
                    pass
                expectedNextCallsCount = ish.nextCallsCount

                stateTester.setup(
                    testCase=self,
                    initialDataSize=iterableSize + skippedBefore,
                    cachedBefore=cachedBefore,
                    skippedBefore=skippedBefore,
                    cachedAfter=max(min(expectedNextCallsCount, iterableSize), cachedBefore),
                )
                stream = stateTester.arrangeStep()

                with self.assertRaises(IndexError):
                    # act1
                    testCase.testCase(stream)

                # assert1
                stateTester.assertStep()

                # arrange2
                stateTester.setup(
                    testCase=self,
                    initialDataSize=iterableSize + skippedBefore,
                    cachedBefore=cachedBefore,
                    skippedBefore=skippedBefore,
                    cachedAfter=max(min(expectedNextCallsCount, iterableSize), cachedBefore),
                )
                stream = stateTester.arrangeStep()

                with self.assertRaises(IndexError):
                    # act2
                    testCase.testCase(stream[0:None])

                # assert2
                stateTester.assertStep()

    # ================================================================================================

    def test_getItem_withSlice_doesNotConsumeSourceOnCreation(self):
        for (index, (skippedBefore, cachedBefore, sliceKey)) in enumerate(itertools.product(
            [0, 3],        # skippedBefore
            [0, 3, 7],     # cachedBefore (visible-view units, after the skip)
            [
                slice(0, 8),
                slice(0, 2),
                slice(4, 0, -1),
                slice(4, None, -1),
                slice(None, None, None),
            ],
        )):
            # remove nullcontext() for more details...but pay a dear execution time price in VSCode
            with nullcontext() or self.subTest(f"index: {index:04d} skippedBefore: {skippedBefore} cachedBefore: {cachedBefore} sliceKey: {sliceKey}"):
                # arrange
                iteratorMock = build_IteratorMock(range(10))
                stream = StreamSequence(iteratorMock)
                stream.consume(skippedBefore)
                preloadData(stream, cachedBefore)
                iteratorMock.__next__.reset_mock()

                # act
                stream[sliceKey]

                # assert
                self.assertEqual(iteratorMock.__next__.call_count, 0)

    def test_getItem_withSliceThenIndex_pullsOnlyAsFarAsNeeded(self):
        for (index, (skippedBefore, (cachedBefore, accessIndex, expectedCalls))) in enumerate(itertools.product(
            [0, 3],        # skippedBefore
            [
                # empty cache → must pull from source
                (0, 0, 1),
                (0, 3, 4),
                # partial cache → pulls only the missing tail
                (2, 0, 0),
                (2, 1, 0),
                (2, 2, 1),
                (2, 5, 4),
                # full cache → no source access
                (8, 0, 0),
                (8, 7, 0),
            ],
        )):
            # remove nullcontext() for more details...but pay a dear execution time price in VSCode
            with nullcontext() or self.subTest(f"index: {index:04d} skippedBefore: {skippedBefore} cachedBefore: {cachedBefore} accessIndex: {accessIndex}"):
                # arrange
                values = list(range(20))
                iteratorMock = build_IteratorMock(values)
                stream = StreamSequence(iteratorMock)
                stream.consume(skippedBefore)
                sliceView = stream[0:8]
                preloadData(sliceView, cachedBefore)
                iteratorMock.__next__.reset_mock()

                # act
                v = sliceView[accessIndex]

                # assert
                self.assertEqual(v, values[skippedBefore:][0:8][accessIndex])
                self.assertEqual(iteratorMock.__next__.call_count, expectedCalls)

    def test_getItem_withSliceThenSubSlice_consumesDataCorrectly(self):
        for (index, (skippedBefore, (cachedBefore, subSlice, accessIndex, expectedCalls))) in enumerate(itertools.product(
            [0, 3],        # skippedBefore
            [
                (0, slice(0, 2), 0, 1),
                (0, slice(0, 2), 1, 2),
                (1, slice(0, 2), 0, 0),
                (1, slice(0, 2), 1, 1),
                (2, slice(0, 2), 0, 0),
                (2, slice(0, 2), 1, 0),
            ],
        )):
            # remove nullcontext() for more details...but pay a dear execution time price in VSCode
            with nullcontext() or self.subTest(f"index: {index:04d} skippedBefore: {skippedBefore} cachedBefore: {cachedBefore} subSlice: {subSlice} accessIndex: {accessIndex}"):
                # arrange
                values = list(range(20))
                iteratorMock = build_IteratorMock(values)
                stream = StreamSequence(iteratorMock)
                stream.consume(skippedBefore)
                sliceView = stream[0:8]
                preloadData(sliceView, cachedBefore)
                iteratorMock.__next__.reset_mock()

                # act
                v = sliceView[subSlice][accessIndex]

                # assert
                self.assertEqual(v, values[skippedBefore:][0:8][subSlice][accessIndex])
                self.assertEqual(iteratorMock.__next__.call_count, expectedCalls)

    def test_getItem_withReverseSlice_consumesDataCorrectly(self):
        # NOTE: the original monolithic test carried "TODO: data is not already
        # available. We should retrieve additional data" comments on a couple
        # of cases. The behaviour encoded below is the current (suboptimal)
        # one; tighten the expected call counts if/when the underlying preload
        # becomes smarter for negative steps.
        for (index, (skippedBefore, (cachedBefore, subSlice, accessIndex, expectedCalls))) in enumerate(itertools.product(
            [0, 3],        # skippedBefore
            [
                # finite stop: pulls enough to bound the window
                (0, slice(4, 0, -1), 3, 5),
                (2, slice(4, 0, -1), 3, 3),
                # stop=None: relies on already-cached prefix
                (5, slice(4, None, -1), 4, 0),
                (5, slice(4, None, -1), 0, 0),
            ],
        )):
            # remove nullcontext() for more details...but pay a dear execution time price in VSCode
            with nullcontext() or self.subTest(f"index: {index:04d} skippedBefore: {skippedBefore} cachedBefore: {cachedBefore} subSlice: {subSlice} accessIndex: {accessIndex}"):
                # arrange
                values = list(range(20))
                iteratorMock = build_IteratorMock(values)
                stream = StreamSequence(iteratorMock)
                stream.consume(skippedBefore)
                sliceView = stream[0:8]
                preloadData(sliceView, cachedBefore)
                iteratorMock.__next__.reset_mock()

                # act
                v = sliceView[subSlice][accessIndex]

                # assert
                self.assertEqual(v, values[skippedBefore:][0:8][subSlice][accessIndex])
                self.assertEqual(iteratorMock.__next__.call_count, expectedCalls)

    def test_getItem_afterPreloadAndSkip_consumesDataCorrectly(self):
        stream = StreamSequence(incrementalValuesGenerator())

        aSlice = stream[0:None]
        preloadData(aSlice, 1)
        stream.consume(1)

        v = aSlice[5]
        self.assertEqual(v, 5)

    def test_invalidated_slice_iterator(self):

        for (index, (cachedBefore, skippedAfter)) in enumerate(itertools.product(
            [0, 3, 10],                             # cachedBefore
            [0, 2],                                 # skippedAfter
        )):
            # remove nullcontext() for more details...but pay a dear execution time price in VSCode
            with nullcontext() or self.subTest(f"index: {index:04d} cachedBefore: {cachedBefore} skippedAfter: {skippedAfter}"):

                stream = StreamSequence(incrementalValuesGenerator())
                preloadData(stream, cachedBefore)

                aSlice = stream[0:None]

                stream.consume(skippedAfter)

                self.assertEqual(aSlice[0], 0)
                self.assertEqual(aSlice[5], 5)

    def test_advanceWithLiveSlice_releasesDataSynchronouslyOnSliceDeletion(self):
        # Values held back only because of a live slice must be released as soon
        # as the slice itself is collected (CPython refcount-driven finalization).

        class Box:
            __slots__ = ('value', '__weakref__')

            def __init__(self, v):
                self.value = v

        for advanceOp in advanceOperations():
            # remove nullcontext() for more details...but pay a dear execution time price in VSCode
            with nullcontext() or self.subTest(f"op: {advanceOp.name}"):
                boxes = [Box(i) for i in range(10)]
                refs = [weakref.ref(b) for b in boxes]

                def drainingSource(items):
                    while items:
                        yield items.pop(0)

                stream = StreamSequence(drainingSource(boxes))
                del boxes  # source drains as it yields; no external strong refs remain

                # Force the parent to cache the first 5 boxes without consuming through the slice.
                stream[4]

                aSlice = stream[0:None]   # anchors the slice at index 0

                advanceOp.apply(stream, 3)

                # While the slice is alive, the first three boxes are still pinned.
                self.assertIsNotNone(refs[0]())
                self.assertIsNotNone(refs[1]())
                self.assertIsNotNone(refs[2]())

                del aSlice
                # PyPy: del → inner iterator → weakref.finalize → _reclaim chain
                # needs more than one gc pass to fully unwind.
                gc.collect()
                gc.collect()

                # Synchronous release of values below the parent's logical index.
                self.assertIsNone(refs[0]())
                self.assertIsNone(refs[1]())
                self.assertIsNone(refs[2]())
                # Values still in the parent's exposed cache remain alive.
                self.assertIsNotNone(refs[3]())
                self.assertIsNotNone(refs[4]())

    def test_advanceWithLiveSlice_releaseBoundedByEarliestOfMultipleSlices(self):
        # When several slices are alive, the earliest one bounds reclamation;
        # deleting it lets the parent release up to the next floor.

        class Box:
            __slots__ = ('value', '__weakref__')

            def __init__(self, v):
                self.value = v

        for advanceOp in advanceOperations():
            # remove nullcontext() for more details...but pay a dear execution time price in VSCode
            with nullcontext() or self.subTest(f"op: {advanceOp.name}"):
                boxes = [Box(i) for i in range(20)]
                refs = [weakref.ref(b) for b in boxes]

                def drainingSource(items):
                    while items:
                        yield items.pop(0)

                stream = StreamSequence(drainingSource(boxes))
                del boxes

                # Pre-cache 10 boxes in the parent.
                stream[9]

                sliceA = stream[0:None]
                sliceB = stream[0:None]

                advanceOp.apply(stream, 5)

                # Both slices anchor the source at index 0 → first boxes still pinned.
                self.assertIsNotNone(refs[0]())

                del sliceA
                # sliceB still anchors at 0 → no release at the front.
                self.assertIsNotNone(refs[0]())

                del sliceB
                # PyPy: del → inner iterator → weakref.finalize → _reclaim chain
                # needs more than one gc pass to fully unwind.
                gc.collect()
                gc.collect()
                # All slices gone: boxes 0..4 release synchronously.
                self.assertIsNone(refs[0]())
                self.assertIsNone(refs[4]())
                self.assertIsNotNone(refs[5]())

    def test_take_returnedListOwnsTheValuesAndReleasesOnDeletion(self):
        # take() transfers ownership: the parent advances past and reclaims the
        # returned values from its cache, so the returned list is their sole
        # owner. Dropping that list collects them (CPython refcount-driven).

        class Box:
            __slots__ = ('value', '__weakref__')

            def __init__(self, v):
                self.value = v

        boxes = [Box(i) for i in range(5)]
        refs = [weakref.ref(b) for b in boxes]

        def drainingSource(items):
            while items:
                yield items.pop(0)

        stream = StreamSequence(drainingSource(boxes))
        del boxes  # source drains as it yields; no external strong refs remain

        taken = stream.take(3)

        # The returned list keeps the first three values alive while held...
        self.assertEqual([box.value for box in taken], [0, 1, 2])
        self.assertIsNotNone(refs[0]())
        self.assertIsNotNone(refs[1]())
        self.assertIsNotNone(refs[2]())

        del taken
        gc.collect()  # PyPy: weakref clearing is not refcount-driven

        # ...and nothing else references them, so they are collected at once.
        self.assertIsNone(refs[0]())
        self.assertIsNone(refs[1]())
        self.assertIsNone(refs[2]())

    def test_iteratingLiveSlice_releasesPrefixAsCursorAdvances(self):
        # Advancing a live sub-iterator must let the parent drop the prefix it
        # was pinning eagerly, step by step, without waiting for GC or another
        # skip()/del. This exercises the per-step _reclaim() in
        # _StreamSequenceIterator.__next__.

        class Box:
            __slots__ = ('value', '__weakref__')

            def __init__(self, v):
                self.value = v

        boxes = [Box(i) for i in range(10)]
        refs = [weakref.ref(b) for b in boxes]

        def drainingSource(items):
            while items:
                yield items.pop(0)

        stream = StreamSequence(drainingSource(boxes))
        del boxes  # source drains as it yields; no external strong refs remain

        # Cache the first boxes in the parent and open a live iterator anchored at 0.
        stream[6]
        iterator = iter(stream)

        # Advance the parent's visible front; the live iterator still pins 0..4.
        stream.consume(5)
        self.assertIsNotNone(refs[0]())
        self.assertIsNotNone(refs[4]())

        # Walk the iterator past boxes 0..4. Each step reclaims the box left
        # behind, because the iterator is now the floor and the visible front
        # already sits at 5.
        for i in range(5):
            next(iterator)
            gc.collect()  # PyPy: weakref clearing is not refcount-driven
            self.assertIsNone(refs[i]())
            self.assertIsNotNone(refs[i + 1]())

    def test_iteratingLiveSlice_releaseBoundedByLaggingIterator(self):
        # With several live iterators, per-step reclamation is bounded by the
        # *earliest* cursor: advancing the leading iterator releases nothing
        # while a lagging one still pins the prefix; only when the laggard
        # advances does the prefix become reclaimable.

        class Box:
            __slots__ = ('value', '__weakref__')

            def __init__(self, v):
                self.value = v

        boxes = [Box(i) for i in range(20)]
        refs = [weakref.ref(b) for b in boxes]

        def drainingSource(items):
            while items:
                yield items.pop(0)

        stream = StreamSequence(drainingSource(boxes))
        del boxes

        # Pre-cache boxes in the parent and open two live iterators anchored at 0.
        stream[9]
        leading = iter(stream)
        lagging = iter(stream)

        stream.consume(5)
        self.assertIsNotNone(refs[0]())
        self.assertIsNotNone(refs[4]())

        # The leading iterator walks past 0..4, but the lagging one still anchors
        # at 0 → the floor stays at 0 and nothing is released.
        for i in range(5):
            next(leading)
            self.assertIsNotNone(refs[i]())

        # Now the laggard advances past 0..4 too → floor reaches 5 and the prefix
        # releases synchronously.
        for i in range(5):
            next(lagging)
            gc.collect()  # PyPy: weakref clearing is not refcount-driven
            self.assertIsNone(refs[i]())
            self.assertIsNotNone(refs[i + 1]())

    def test_getItem_withNegativeIndexOutOfBound_withHeldBackPrefix_raisesIndexError(self):
        # A live sub-iterator pins the skipped prefix in the cache. A negative
        # index beyond the visible view must still raise IndexError and must not
        # silently return a held-back prefix value (regression guard for the
        # copy-free negative indexing path).
        iterableSize = 10
        for (index, (skippedBefore, cachedBefore)) in enumerate(itertools.product(
            [0, 2, 5],   # skippedBefore: prefix pinned by the live iterator
            [0, 3, 7],   # cachedBefore: visible units preloaded before indexing
        )):
            # remove nullcontext() for more details...but pay a dear execution time price in VSCode
            with nullcontext() or self.subTest(f"index: {index:04d} skippedBefore: {skippedBefore} cachedBefore: {cachedBefore}"):
                # arrange
                stream = StreamSequence(iter(range(iterableSize)))
                liveIterator = iter(stream)   # anchors and pins the prefix at index 0
                stream.consume(skippedBefore)
                preloadData(stream, cachedBefore)

                visibleLen = iterableSize - skippedBefore

                # in-range negative indices address the visible view, not the prefix
                self.assertEqual(stream[-1], iterableSize - 1)
                self.assertEqual(stream[-visibleLen], skippedBefore)

                # one past the visible front: must raise, not return the pinned prefix
                with self.assertRaises(IndexError):
                    stream[-(visibleLen + 1)]

                # the prefix really was held back (still reachable via the live iterator)
                self.assertEqual(next(liveIterator), 0)

    def test_getitem_withSlice_acrossParentBufferingAndSkip_sliceIndependent(self):
        # A slice keeps the elements it would have yielded at creation time,
        # regardless of how the parent is buffered or skipped both *before* and
        # *after* the slice is created, and for both full and bounded slices.
        # Caching never changes logical content; only a skip *before* creation
        # shifts the parent front the slice captures.
        iterableSize = 10
        reference = list(range(iterableSize))

        for (index, (sliceBounds, cachedBefore, cachedAfter, skippedBefore, skippedAfter)) in enumerate(itertools.product(
            [(0, None), (2, 8)],                    # slice bounds: full and bounded
            [0, 3, 10],                             # elements cached before the slice is created
            [0, 3, 10],                             # elements cached after the slice is created
            [0, 2],                                 # elements skipped before the slice is created
            [0, 2],                                 # elements skipped after the slice is created
        )):
            start, stop = sliceBounds
            # remove nullcontext() for more details...but pay a dear execution time price in VSCode
            with nullcontext() or self.subTest(f"index: {index:04d} sliceBounds: {sliceBounds} cachedBefore: {cachedBefore} cachedAfter: {cachedAfter} skippedBefore: {skippedBefore} skippedAfter: {skippedAfter}"):  # noqa: E501

                stream = StreamSequence(iter(range(iterableSize)))

                # before the slice is created
                stream.consume(skippedBefore)
                preloadData(stream, cachedBefore)

                aSlice = stream[start:stop]

                # after the slice is created
                preloadData(stream, cachedAfter)
                taken = stream.take(skippedAfter)

                # the slice captured the parent front at creation (skippedBefore)
                expectedSlice = reference[skippedBefore:][start:stop]
                self.assertEqual(aSlice[0], expectedSlice[0])
                self.assertEqual(aSlice[5], expectedSlice[5])
                self.assertEqual(list(aSlice), expectedSlice)

                # the parent reflects both skips
                self.assertEqual(taken, reference[skippedBefore:skippedBefore + skippedAfter])
                self.assertEqual(stream[0], skippedBefore + skippedAfter)
                self.assertEqual(len(stream), iterableSize - (skippedBefore + skippedAfter))

    def test_advance_onSliceResult_advancesWithinSlicedView(self):
        # A slice result is itself a first-class StreamSequence: take()/consume()
        # must operate within the sliced sub-stream, independently of the parent.
        iterableSize = 20
        reference = list(range(iterableSize))
        for (index, (advanceOp, sliceBounds, advanceCount)) in enumerate(itertools.product(
            advanceOperations(),    # advanceOp
            [(2, 12), (5, None)],   # slice bounds: bounded and open-ended
            [0, 3, 100],            # values to advance from the slice (100 over-advances)
        )):
            start, stop = sliceBounds
            # remove nullcontext() for more details...but pay a dear execution time price in VSCode
            with nullcontext() or self.subTest(f"index: {index:04d} op: {advanceOp.name} sliceBounds: {sliceBounds} advanceCount: {advanceCount}"):  # noqa: E501
                # arrange
                stream = StreamSequence(iter(range(iterableSize)))
                aSlice = stream[start:stop]
                expectedSlice = reference[start:stop]

                # act
                result = advanceOp.apply(aSlice, advanceCount)

                # assert: returns the leading sliced values (or None), capped at what exists
                expectedAdvanced = expectedSlice[:advanceCount]
                self.assertEqual(result, advanceOp.expectedReturn(expectedAdvanced))
                # the remaining slice view reflects the advance, independently of the parent
                self.assertEqual(list(aSlice), expectedSlice[len(expectedAdvanced):])
                self.assertEqual(len(aSlice), len(expectedSlice) - len(expectedAdvanced))
                # the parent is untouched by advancing the slice
                self.assertEqual(stream[0], 0)

    # ==== repr ===

    def test_repr_doesNotConsumeSource(self):
        # On a fresh view nothing has been pulled yet...
        freshMock = build_IteratorMock(range(100))
        fresh = StreamSequence(freshMock)
        repr(fresh)
        self.assertEqual(freshMock.__next__.call_count, 0)

        # ...and once some values are buffered, repr must not pull any further.
        bufferedMock = build_IteratorMock(range(100))
        stream = StreamSequence(bufferedMock)
        preloadData(stream=stream, preload=4)
        bufferedMock.__next__.reset_mock()
        repr(stream)
        self.assertEqual(bufferedMock.__next__.call_count, 0)

    def test_repr_onFreshSequence_showsEmptyBufferedWindow(self):
        stream = StreamSequence(range(10))

        text = repr(stream)

        self.assertTrue(text.startswith("<StreamSequence "))
        self.assertTrue(text.endswith(">"))
        self.assertIn("buffered=0", text)
        self.assertIn("heldBack=0", text)
        self.assertIn("preview=[]", text)

    def test_repr_afterBuffering_showsBufferedValues(self):
        stream = StreamSequence(range(10))
        stream[3]   # buffer values 0..3

        text = repr(stream)

        self.assertIn("buffered=4", text)
        self.assertIn("heldBack=0", text)
        self.assertIn("preview=[0, 1, 2, 3]", text)

    def test_repr_afterConsume_showsShiftedWindow(self):
        stream = StreamSequence(range(10))
        stream[3]            # buffer values 0..3
        stream.consume(2)    # advance the visible front past 0, 1

        text = repr(stream)

        self.assertIn("buffered=2", text)
        self.assertIn("heldBack=0", text)
        self.assertIn("preview=[2, 3]", text)

    def test_repr_truncatesPreviewBeyondLimit(self):
        stream = StreamSequence(range(100))
        stream[20]   # buffer 21 values (0..20)

        text = repr(stream)

        self.assertIn("buffered=21", text)
        self.assertIn("preview=[0, 1, 2, 3, 4, 5, 6, 7, ...]", text)

    def test_repr_withLiveSlice_reportsHeldBackPrefix(self):
        stream = StreamSequence(range(10))
        stream[4]                     # buffer values 0..4
        liveSlice = stream[0:None]    # pins the prefix at index 0
        stream.consume(3)             # visible front advances; prefix held for the slice

        text = repr(stream)

        self.assertIn("heldBack=3", text)
        self.assertIn("preview=[3, 4]", text)
        self.assertIsNotNone(liveSlice)  # keep the slice alive across the repr call

    def test_repr_showsExhaustedState(self):
        stream = StreamSequence(range(3))
        self.assertIn("exhausted=False", repr(stream))   # nothing pulled yet

        stream.consume(None)                             # drain the source
        self.assertIn("exhausted=True", repr(stream))

    def test_repr_showsLiveSubIteratorCount(self):
        stream = StreamSequence(range(10))
        self.assertIn("subIterators=0", repr(stream))

        liveSlice = stream[0:None]
        self.assertIn("subIterators=1", repr(stream))
        self.assertIsNotNone(liveSlice)  # keep the slice alive across the repr call

    # ==== Sequence mixins (regression guard) ===

    def test_sequenceMixins_workOnBoundedSource(self):
        # __contains__, index, count, and reversed() are inherited from
        # collections.abc.Sequence. They consume the source (partially or
        # fully — see the class docstring "Sequence-mixin caveats"). On a
        # bounded source they must still produce the standard results;
        # this guards against an accidental override.
        cases = [
            ("__contains__ hit", lambda p: 2 in p, True),           # noqa: E272
            ("__contains__ miss", lambda p: 99 in p, False),          # noqa: E272
            ("index", lambda p: p.index(2), 2),              # noqa: E272
            ("count distinct", lambda p: p.count(2), 1),              # noqa: E272
            ("count missing", lambda p: p.count(99), 0),              # noqa: E272
            ("reversed", lambda p: list(reversed(p)), [4, 3, 2, 1, 0]),  # noqa: E272
        ]
        for label, operation, expected in cases:
            with self.subTest(label):
                stream = StreamSequence(range(5))
                self.assertEqual(operation(stream), expected)
