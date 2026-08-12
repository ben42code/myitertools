import itertools
import unittest
from collections.abc import Iterator
from typing import NamedTuple

from ben42code.myitertools import IteratorCounter, collapse


class Case(NamedTuple):
    source: list
    expected: list


class Tag:
    def __init__(self, text: str):
        self.text = text


class Collapse_Test(unittest.TestCase):

    def test_alreadyFlat_returnsSameValues(self):
        result = list(collapse([1, 2, 3]))
        self.assertEqual(result, [1, 2, 3])

    def test_nesting_flattensDepthFirst(self):
        testcases = [
            Case(source=[1, [2, 3], 4],
                 expected=[1, 2, 3, 4]),
            Case(source=[[1, 2], 3, 4],                 # nested first child
                 expected=[1, 2, 3, 4]),
            Case(source=[1, 2, [3, 4]],                 # nested last child
                 expected=[1, 2, 3, 4]),
            Case(source=[[1, 2], 3, [4, 5]],            # nested first and last
                 expected=[1, 2, 3, 4, 5]),
            Case(source=[[[1]], 2, [[3]]],              # nested at both ends, deeper
                 expected=[1, 2, 3]),
            Case(source=[1, [2, [3, [4, 5], 6], 7], 8],
                 expected=[1, 2, 3, 4, 5, 6, 7, 8]),
            Case(source=[1, (2, 3), [4, iter([5, 6])], range(7, 9)],
                 expected=[1, 2, 3, 4, 5, 6, 7, 8]),
        ]
        for testcase in testcases:
            with self.subTest(source=testcase.source):
                result = list(collapse(testcase.source))
                self.assertEqual(result, testcase.expected)

    def test_emptyIterables_skipped(self):
        testcases = [
            Case(source=[],
                 expected=[]),
            Case(source=[[], [[]], [[], []]],
                 expected=[]),
            Case(source=[[], 1, []],                    # empties around a leaf
                 expected=[1]),
            Case(source=[[], [1, 2], []],               # empties around a nested list
                 expected=[1, 2]),
            Case(source=[1, [], 2, [[]], 3],            # empties interleaved with leaves
                 expected=[1, 2, 3]),
            Case(source=[[[], 1], [2, []]],             # empty as first/last within nesting
                 expected=[1, 2]),
        ]
        for testcase in testcases:
            with self.subTest(source=testcase.source):
                result = list(collapse(testcase.source))
                self.assertEqual(result, testcase.expected)

    def test_nonIterableLeaves_yielded(self):
        marker = object()
        result = list(collapse([1, None, marker]))
        self.assertEqual(result, [1, None, marker])

    def test_defaultAtoms_keptWhole(self):
        testcases = [
            Case(source=[1, "AB", 2], expected=[1, "AB", 2]),
            Case(source=[1, b"AB", 2], expected=[1, b"AB", 2]),
        ]
        for testcase in testcases:
            with self.subTest(testcase):
                self.assertEqual(list(collapse(testcase.source)), testcase.expected)

    def test_atomsEmpty_bytesExpandToInts(self):
        # bytes only: atoms=() on a str would not terminate (chars stay str).
        self.assertEqual(list(collapse([1, b"AB", 2], atoms=())), [1, 65, 66, 2])

    def test_atomsCustom_treatsTypeAsLeaf(self):
        source = [1, [2, 3], 4]
        self.assertEqual(list(collapse([source], atoms=(list,))), [source])

    def test_handler_replacesElement(self):
        handlers = {str: lambda s: s.encode("ascii")}
        result = list(collapse([10, "AB", 20], handlers=handlers, atoms=()))
        self.assertEqual(result, [10, 65, 66, 20])

    def test_handler_resultIsReflattened(self):
        handlers = {
            Tag: lambda t: t.text,
            str: lambda s: s.encode("ascii"),
        }
        result = list(collapse([10, Tag("AB"), 20], handlers=handlers, atoms=()))
        self.assertEqual(result, [10, 65, 66, 20])

    def test_handler_takesPrecedenceOverAtoms(self):
        # str is an atom by default, but a str handler must still win.
        handlers = {str: lambda s: [ord(c) for c in s]}
        result = list(collapse([1, "AB", 2], handlers=handlers))
        self.assertEqual(result, [1, 65, 66, 2])

    def test_handler_returningNonIterable_yieldedAsLeaf(self):
        handlers = {Tag: lambda t: len(t.text)}
        result = list(collapse([Tag("AB"), Tag("CDE")], handlers=handlers))
        self.assertEqual(result, [2, 3])

    def test_handler_returningEmpty_dropsElement(self):
        handlers = {Tag: lambda t: []}
        result = list(collapse([1, Tag("x"), 2], handlers=handlers))
        self.assertEqual(result, [1, 2])

    def test_handler_appliesAtAnyDepth(self):
        handlers = {str: lambda s: s.encode("ascii")}
        source = [1, [2, "AB"], 3]
        result = list(collapse(source, handlers=handlers, atoms=()))
        self.assertEqual(result, [1, 2, 65, 66, 3])

    def test_returnsIterator(self):
        result = collapse([1, [2, 3]])
        self.assertIsInstance(result, Iterator)
        self.assertEqual(next(result), 1)

    def test_construction_pullsNothing(self):
        source = IteratorCounter([[1, 2], [3, 4]])
        collapse(source)
        self.assertEqual(source.count, 0)

    def test_lazy_pullsIncrementally(self):
        def nested_infinite():
            for i in itertools.count():
                yield [i, [i * 10]]

        source = IteratorCounter(nested_infinite())
        it = collapse(source)

        # (expected value, source.count expected AFTER pulling that value):
        # pulls are interleaved with yields, so only the item actually needed
        # for the next leaf is ever pulled from the source.
        expectations = [(0, 1), (0, 1), (1, 2), (10, 2), (2, 3)]
        for value, count in expectations:
            self.assertEqual(next(it), value)
            self.assertEqual(source.count, count)

    def test_deepNesting_noRecursionError(self):
        deep = 0
        for _ in range(10_000):
            deep = [deep]
        self.assertEqual(list(collapse([deep])), [0])

    def test_bytePayload_fromComposedConstants(self):
        # Assemble a byte payload from nested 7-bit control constants that are
        # themselves composed from other constants (a common protocol pattern).
        ESC = 0x1B
        HEADER = [ESC, 0x3A]
        FRAME = [HEADER, 0x73]

        class TestCase(NamedTuple):
            source: list
            payload: bytes

        testcases = [
            TestCase(source=[HEADER], payload=bytes([0x1B, 0x3A])),
            TestCase(source=[FRAME], payload=bytes([0x1B, 0x3A, 0x73])),
            TestCase(source=[10, "AB", [11, b"\x01\x02", 19], 20],
                     payload=bytes([10, 65, 66, 11, 1, 2, 19, 20])),
        ]

        handlers = {str: lambda s: s.encode("ascii")}
        for testcase in testcases:
            with self.subTest(testcase):
                result = bytes(collapse(testcase.source, handlers=handlers, atoms=()))
                self.assertEqual(result, testcase.payload)


if __name__ == '__main__':
    unittest.main(verbosity=2)
