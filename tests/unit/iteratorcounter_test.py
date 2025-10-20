import unittest
from itertools import islice
from typing import Iterator, NamedTuple
from unittest.mock import Mock

from ben42code.myitertools import IteratorCounter


def build_IterableMock(iterator: Iterator) -> Mock:
    IteratorMock = Mock()
    IteratorMock.__iter__ = Mock(return_value=iterator)
    return IteratorMock


def build_IteratorMock(side_effect) -> Mock:
    IteratorMock = Mock()
    IteratorMock.__iter__ = Mock(return_value=IteratorMock)
    IteratorMock.__next__ = Mock(side_effect=side_effect)
    return IteratorMock


class TestIteratorCounter(unittest.TestCase):
    def test_constructor_withIterator_expectedState(self):
        # arrange
        iteratorMock = build_IteratorMock([1, 2, 3])

        # act
        counterIterator = IteratorCounter(iteratorMock)

        # assert
        self.assertEqual(counterIterator.count, 0)
        self.assertEqual(iteratorMock.__iter__.call_count, 1)
        self.assertEqual(iteratorMock.__next__.call_count, 0)

    def test_constructor_withIterable_expectedState(self):
        # arrange
        iteratorMock = build_IteratorMock([1, 2, 3])
        iterableMock = build_IterableMock(iteratorMock)

        # act
        counterIterator = IteratorCounter(iterableMock)

        # assert
        self.assertEqual(counterIterator.count, 0)
        self.assertEqual(iterableMock.__iter__.call_count, 1)
        self.assertEqual(iteratorMock.__iter__.call_count, 0)
        self.assertEqual(iteratorMock.__next__.call_count, 0)

    def test_iter_withIterator_self(self):
        # arrange
        iteratorMock = build_IteratorMock([1, 2, 3])
        counterIterator = IteratorCounter(iteratorMock)
        iteratorMock.__iter__.call_count = 0

        # act
        result = iter(counterIterator)

        # assert
        self.assertIs(result, counterIterator)
        self.assertEqual(iteratorMock.__iter__.call_count, 0)
        self.assertEqual(iteratorMock.__next__.call_count, 0)

    def test_iter_withIterable_self(self):
        # arrange
        iteratorMock = build_IteratorMock([1, 2, 3])
        iterableMock = build_IterableMock(iteratorMock)
        counterIterator = IteratorCounter(iterableMock)
        iterableMock.__iter__.call_count = 0

        # act
        result = iter(counterIterator)

        # assert
        self.assertIs(result, counterIterator)
        self.assertEqual(iterableMock.__iter__.call_count, 0)
        self.assertEqual(iteratorMock.__iter__.call_count, 0)
        self.assertEqual(iteratorMock.__next__.call_count, 0)

    def test_next_withVariousCases_expectedResults(self):
        class TestCase(NamedTuple):
            input_data: list
            consume_count: int | None
            expected_result: list | None
            expected_count: int

        test_cases = [
            TestCase(input_data=[10, 20, 30], consume_count=3, expected_result=[10, 20, 30], expected_count=3),
            TestCase(input_data=[], consume_count=0, expected_result=[], expected_count=0),
            TestCase(input_data=[1, 2, 3, 4], consume_count=2, expected_result=[1, 2], expected_count=2),
        ]
        for index, test_case in enumerate(test_cases):
            with self.subTest(index=index, data=test_case.input_data, consume_count=test_case.consume_count):
                # arrange
                iteratorMock = build_IteratorMock(test_case.input_data)
                counterIterator = IteratorCounter(iteratorMock)

                # act
                result = list(islice(counterIterator, test_case.consume_count))

                # assert
                self.assertEqual(result, test_case.expected_result)
                self.assertEqual(counterIterator.count, test_case.expected_count)
                self.assertEqual(iteratorMock.__iter__.call_count, 1)
                self.assertEqual(iteratorMock.__next__.call_count, test_case.expected_count)

    def test_next_whenStopIteration_expectedResult(self):
        class TestCase(NamedTuple):
            input_data: list

        test_cases = [
            TestCase(input_data=[10, 20, 30]),
            TestCase(input_data=[]),
        ]
        for index, input_data in enumerate(test_cases):
            with self.subTest(index=index, input_data=input_data):
                # arrange
                iteratorMock = build_IteratorMock(input_data)
                counterIterator = IteratorCounter(iteratorMock)
                iteratorMock.__iter__.call_count = 0

                # act
                list(counterIterator)

                # assert
                self.assertEqual(counterIterator.count, len(input_data))
                self.assertEqual(iteratorMock.__iter__.call_count, 0)
                self.assertEqual(iteratorMock.__next__.call_count, len(input_data) + 1)

                # arrange
                iteratorMock.__next__.call_count = 0

                # act & assert
                with self.assertRaises(StopIteration):
                    next(counterIterator)

                # assert
                self.assertEqual(counterIterator.count, len(input_data))
                self.assertEqual(iteratorMock.__iter__.call_count, 0)
                self.assertEqual(iteratorMock.__next__.call_count, 1)


if __name__ == '__main__':
    unittest.main(verbosity=2)
