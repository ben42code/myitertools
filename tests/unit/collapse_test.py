import itertools
import unittest
from typing import NamedTuple

from ben42code.myitertools import IteratorCounter, collapse


class Tag:
    def __init__(self, text: str):
        self.text = text


class Collapse_Test(unittest.TestCase):

    def test_alreadyFlat_returnsSameValues(self):
        self.assertEqual(list(collapse([1, 2, 3])), [1, 2, 3])

    def test_nested_flattensDepthFirst(self):
        self.assertEqual(list(collapse([1, [2, 3], 4])), [1, 2, 3, 4])

    def test_deeplyNested_flattensDepthFirst(self):
        source = [1, [2, [3, [4, 5], 6], 7], 8]
        self.assertEqual(list(collapse(source)), [1, 2, 3, 4, 5, 6, 7, 8])

    def test_mixedIterableTypes_flattened(self):
        source = [1, (2, 3), [4, iter([5, 6])], range(7, 9)]
        self.assertEqual(list(collapse(source)), [1, 2, 3, 4, 5, 6, 7, 8])

    def test_empty_yieldsNothing(self):
        self.assertEqual(list(collapse([])), [])

    def test_nestedEmpties_yieldsNothing(self):
        self.assertEqual(list(collapse([[], [[]], [[], []]])), [])

    def test_nonIterableLeaves_yielded(self):
        marker = object()
        self.assertEqual(list(collapse([1, None, marker])), [1, None, marker])

    def test_string_keptWholeByDefault(self):
        self.assertEqual(list(collapse([1, "AB", 2])), [1, "AB", 2])

    def test_bytes_keptWholeByDefault(self):
        self.assertEqual(list(collapse([1, b"AB", 2])), [1, b"AB", 2])

    def test_atomsEmpty_bytesExpandToInts(self):
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

    def test_handler_appliesAtAnyDepth(self):
        handlers = {str: lambda s: s.encode("ascii")}
        source = [1, [2, "AB"], 3]
        result = list(collapse(source, handlers=handlers, atoms=()))
        self.assertEqual(result, [1, 2, 65, 66, 3])

    def test_returnsLazyIterator(self):
        result = collapse([1, [2, 3]])
        self.assertNotIsInstance(result, list)
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

    def test_minitelLike_composedConstants(self):
        ESC = 0x1B
        PRO2 = [ESC, 0x3A]
        PRO2_REP_STATUS_VITESSE = [PRO2, 0x73]

        class TestCase(NamedTuple):
            source: list
            payload: bytes

        testcases = [
            TestCase(source=[PRO2], payload=bytes([0x1B, 0x3A])),
            TestCase(source=[PRO2_REP_STATUS_VITESSE], payload=bytes([0x1B, 0x3A, 0x73])),
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
