# ben42code.myitertools
Providing some additional capabilities on top of [`itertools`](https://docs.python.org/3/library/itertools.html).

Everything here is lazy and stream-friendly: values are pulled from the source
only as far as the requested result requires.

## Installation
```console
pip install ben42code.myitertools
```
Requires Python 3.10+.

## Features
| Feature | Intent |
| --- | --- |
| [`islice_extended`](#islice_extended) | `itertools.islice` with negative `start`/`stop`/`step` support. |
| [`IteratorCounter`](#iteratorcounter) | Transparent wrapper that counts the values pulled through it. |
| [`StreamSequence`](#streamsequence) | A lazy `Sequence` view (`len`, indexing, slicing) over a one-shot iterator. |

> The `>>>` examples below are executed as
> [doctests](https://docs.python.org/3/library/doctest.html) by the test suite,
> so they are guaranteed to stay in sync with the code.

## `islice_extended`
```python
islice_extended(iterable: Iterable[T], stop: int | None) -> Iterator[T]
islice_extended(iterable: Iterable[T], start: int | None, stop: int | None, step: int | None = 1) -> Iterator[T]
```
Slice any iterable the way `list[start:stop:step]` would — including negative
`start`/`stop` indices and a negative `step` — pulling from the source lazily
instead of materialising it up front.

```python
>>> from ben42code.myitertools import islice_extended
>>> list(islice_extended([0, 1, 2, 3, 4, 5, 6, 7, 8, 9], -1, -5, -1))
[9, 8, 7, 6]
>>> list(islice_extended([0, 1, 2], None, None, -1))
[2, 1, 0]

```

**Notes**
- Non-negative bounds + positive step → pure `itertools.islice` delegation, O(1) extra memory.
- ⚠️ A negative `start`/`stop` must find the end of the stream: the input is consumed to exhaustion and buffered — O(n) time and memory (**hangs on an unbounded source**).
- A negative `step` (with non-negative bounds) buffers up to `start + 1` values — O(start).
- Buffered values are released as they are yielded, so retained memory shrinks while you iterate.

## `IteratorCounter`
```python
IteratorCounter(iterator: Iterator[T] | Iterable[T])
count: int  # values pulled from the source so far
```
Wrap an iterator/iterable and expose, at any time, how many values have been
pulled through it — without changing what flows downstream.

```python
>>> from itertools import islice
>>> from ben42code.myitertools import IteratorCounter
>>> wrapper = IteratorCounter('ABCDEFGHIJKLMNOP')
>>> list(islice(wrapper, 2, 5))
['C', 'D', 'E']
>>> wrapper.count
5

```

**Notes**
- Fully lazy and single-pass: O(1) time per value, O(1) extra memory.
- `.count` reflects values *actually pulled* from the source, so it doubles as a probe of how far a downstream consumer really advanced the stream (e.g. `islice(_, 2, 5)` pulls `5`, not `3`).

## `StreamSequence`
```python
StreamSequence(iterable: Iterable[T])
take(n: int | None) -> list[T]     # advance the visible front, returning the values
consume(n: int | None) -> None     # advance the visible front, discarding the values
```
Expose a one-shot iterator/iterable (generator, file, socket, `itertools` chain …)
through the
[`collections.abc.Sequence`](https://docs.python.org/3/library/collections.abc.html#collections.abc.Sequence)
protocol — `len()`, positive/negative indexing, iteration and slicing — while
still consuming the source lazily.

```python
>>> from itertools import count
>>> from ben42code.myitertools import StreamSequence
>>> stream = StreamSequence(count(0))   # unbounded source
>>> stream[3]                           # pulls only 0..3
3
>>> stream.take(3)
[0, 1, 2]
>>> stream[0]                           # the visible front has advanced
3
>>> StreamSequence(count(0))[::2].take(5)   # lazy slice over an unbounded source
[0, 2, 4, 6, 8]

```

**Notes**
- On-demand: a non-negative index or `take(n)` pulls only as far as needed; with no live sub-iterators, `consume`/`take` stream straight past the cache — O(1) retained memory on a self-draining source.
- Slices and previously created iterators keep their own anchor, so they still see values the parent moved past; buffering is bounded to what live sub-iterators hold back, and released values are tombstoned and compacted in amortised O(1).
- ⚠️ Operations that must reach the end — `len()`, negative indexing, `__contains__`/`index` on a miss, `count`, `reversed` — walk the source to exhaustion and **hang on an unbounded stream**; use them only on a bounded view.
- Built for one-shot sources: wrapping a random-access `Sequence` (`list`, `tuple`, `range` …) only adds indirection — use it directly instead.
- ⚠️ Not thread-safe: a `StreamSequence` and its sub-iterators need external synchronisation for concurrent use.

---
[![PyPI version](https://img.shields.io/pypi/v/ben42code.myitertools)](https://pypi.org/project/ben42code.myitertools/)
[![PyPI Downloads](https://static.pepy.tech/badge/ben42code-myitertools)](https://pepy.tech/projects/ben42code-myitertools)
[![PyPI - Downloads](https://img.shields.io/pypi/dm/ben42code.myitertools)](https://pypistats.org/packages/ben42code.myitertools)
