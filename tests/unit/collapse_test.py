import abc
import itertools
import unittest
from collections.abc import Iterator
from typing import NamedTuple

from ben42code.myitertools import IteratorCounter, collapse


class Case(NamedTuple):
    source: list
    expected: list


# --- test fixtures ---

class Tag:
    def __init__(self, text: str):
        self.text = text


class Base:
    def __init__(self, value):
        self.value = value


class Derived(Base):
    pass


class Drawable(abc.ABC):
    pass


class Point:
    def __init__(self, value):
        self.value = value


Drawable.register(Point)               # virtual subclass: Drawable is not in Point.__mro__


class Alpha(abc.ABC):
    pass


class Beta(abc.ABC):
    pass


class Gamma:
    pass


# Virtual registration makes both issubclass checks true without adding either
# ABC to Gamma.__mro__. Since Alpha and Beta are unrelated, singledispatch has
# no inheritance order by which it can prefer one registration over the other.
Alpha.register(Gamma)
Beta.register(Gamma)


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

    def test_handlerForDefaultAtomType_overridesDefault(self):
        # str is a default atom, but registering a str handler drops that
        # default so the handler applies instead.
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
        ESC = 0x1B
        SEP = 0x13
        PRO2 = [ESC, 0x3A]
        PRO3 = [ESC, 0x3B]
        MIXTE1 = [0x32, 0x7D]
        TELINFO = [0x31, 0x7D]
        PRO2_MIXTE1 = [PRO2, MIXTE1]
        PRO2_TELINFO = [PRO2, TELINFO]
        PRO3_REP_STATUS_KEYBOARD = [PRO3, 0x73]
        CSI_VIDEOTEX_TO_MIXTE = [SEP, 0x70]

        class PayloadCase(NamedTuple):
            source: list
            payload: bytes

        testcases = [
            PayloadCase(
                source=[PRO2_MIXTE1, CSI_VIDEOTEX_TO_MIXTE],
                payload=bytes([0x1B, 0x3A, 0x32, 0x7D, 0x13, 0x70]),
            ),
            PayloadCase(
                source=[PRO3_REP_STATUS_KEYBOARD, 0x51, b"\x01\x02"],
                payload=bytes([0x1B, 0x3B, 0x73, 0x51, 0x01, 0x02]),
            ),
            PayloadCase(
                source=[10, "AB", [PRO2_TELINFO, [11, b"\x01\x02"]], 20],
                payload=bytes([
                    10, 65, 66, 0x1B, 0x3A, 0x31, 0x7D, 11, 1, 2, 20
                ]),
            ),
        ]

        handlers = {str: lambda s: s.encode("ascii")}
        for testcase in testcases:
            with self.subTest(testcase):
                result = bytes(collapse(testcase.source, handlers=handlers, atoms=()))
                self.assertEqual(result, testcase.payload)

    def test_bytePayload_withNonAsciiText_raisesUnicodeEncodeError(self):
        handlers = {str: lambda s: s.encode("ascii")}
        result = collapse([0x1B, "café"], handlers=handlers, atoms=())
        with self.assertRaises(UnicodeEncodeError):
            bytes(result)

    def test_atomOnSubtype_excludesFromParentHandler(self):
        base, derived = Base(1), Derived(2)
        handlers = {Base: lambda b: [b.value]}
        result = list(collapse([base, derived], handlers=handlers, atoms=(Derived,)))
        self.assertEqual(result, [1, derived])   # base transformed, derived kept whole

    def test_handlerOnSubtype_overridesParentAtom(self):
        base, derived = Base(1), Derived(2)
        handlers = {Derived: lambda d: [d.value]}
        result = list(collapse([base, derived], handlers=handlers, atoms=(Base,)))
        self.assertEqual(result, [base, 2])      # base kept whole, derived transformed

    def test_mostSpecificHandlerWins_orderIndependent(self):
        # Both registration orders must resolve a Derived to the Derived handler.
        for handlers in (
            {Base: lambda b: [1], Derived: lambda d: [2]},
            {Derived: lambda d: [2], Base: lambda b: [1]},
        ):
            with self.subTest(order=[t.__name__ for t in handlers]):
                self.assertEqual(list(collapse([Derived(0)], handlers=handlers)), [2])

    def test_abcVirtualSubclass_resolvedByHandler(self):
        # Point is a virtual subclass of Drawable (not in its MRO).
        handlers = {Drawable: lambda d: [d.value]}
        result = list(collapse([1, Point(7), 2], handlers=handlers, atoms=()))
        self.assertEqual(result, [1, 7, 2])

    def test_explicitAtomHandlerConflict_raisesValueError(self):
        with self.assertRaises(ValueError):
            collapse([1], handlers={str: lambda s: s}, atoms=(str,))

    def test_ambiguousResolution_raisesValueError(self):
        # Gamma virtually matches both unrelated handler types, so neither is
        # more specific. Resolution is lazy; the error occurs during iteration.
        handlers = {Alpha: lambda x: [1], Beta: lambda x: [2]}
        result = collapse([Gamma()], handlers=handlers, atoms=())
        with self.assertRaises(ValueError):
            list(result)


if __name__ == '__main__':
    unittest.main(verbosity=2)
