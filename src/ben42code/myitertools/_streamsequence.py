"""
StreamSequence — a ``Sequence`` view over a one-shot iterator/iterable.

Wraps any iterator or iterable and exposes it through the
``collections.abc.Sequence`` protocol (``len``, indexing, iteration,
slicing) while consuming the underlying source lazily — values are
pulled only when a method actually needs one.

See ``StreamSequence`` for slicing, retention, and holdback semantics.

Not thread-safe.
"""
from __future__ import annotations

import itertools
import weakref
from typing import Iterable, Iterator, Sequence, SupportsIndex, TypeVar

from ben42code.myitertools import islice_extended

__all__ = ["StreamSequence"]

T = TypeVar('T')


class _StreamSequenceIterator(Iterator[T]):
    """
    Internal iterator backing ``StreamSequence.__iter__`` and the slice path
    in ``StreamSequence.__getitem__``.

    Anchors on the source at an absolute index (``_cursorAbsoluteIndex``) and registers
    in the parent's ``_liveSubIterators`` WeakSet, so the parent retains any
    cache entries this iterator can still reach. Each ``__next__`` — and a
    ``weakref`` finalizer on collection — calls the parent's ``_reclaim()`` to
    release values once they fall out of reach.

    ``_cursorAbsoluteIndex`` may legitimately trail the parent's ``_visibleAbsoluteIndex``: that is
    the holdback this class enables — the parent advanced its visible front via
    ``take()``/``consume()`` while this iterator still reads earlier values.
    """

    __slots__ = ('_parentStreamSequence', '_cursorAbsoluteIndex', '__weakref__')

    def __init__(self, parentStreamSequence: StreamSequence[T]):
        assert isinstance(parentStreamSequence, StreamSequence)
        self._parentStreamSequence = parentStreamSequence
        # Anchor at the parent's visible front so a new iterator never reaches
        # values the parent has already advanced past.
        self._cursorAbsoluteIndex = parentStreamSequence._visibleAbsoluteIndex

        parentStreamSequence._liveSubIterators.add(self)
        # Ensure the parent reclaims any data this iterator was pinning
        # as soon as the iterator is collected. The callback intentionally
        # does not capture `self` (would prevent collection).
        weakref.finalize(self, parentStreamSequence._reclaim)

    def __next__(self) -> T:
        parentStream = self._parentStreamSequence

        parentStream._preloadUpTo(absoluteEndIndex=self._cursorAbsoluteIndex + 1)

        found, value = parentStream._tryGetAtAbsoluteIndex(self._cursorAbsoluteIndex)
        if not found:
            raise StopIteration  # end of stream reached

        self._cursorAbsoluteIndex += 1
        parentStream._reclaim()
        return value


class StreamSequence(Sequence[T]):
    """
    A ``Sequence`` view over a one-shot iterator or iterable.

    Wraps any ``Iterator[T]`` or ``Iterable[T]`` and exposes it through the
    ``collections.abc.Sequence`` protocol — supporting ``len()``, indexing
    (positive and negative), iteration, and slicing — while consuming the
    underlying source lazily: a value is pulled from the source only when
    a method actually needs it.

    Slicing semantics:
        ``stream[start:stop:step]`` returns a new ``StreamSequence``
        that views the same source through the requested slice. The returned
        generator pulls from the parent on demand and caches its own values
        independently.

    Non-goal — random-access inputs:
        ``StreamSequence`` is built for one-shot, lazily-consumed sources
        (file/socket/serial streams, generators, ``itertools`` chains …).
        If you already have a random-access ``Sequence`` (``list``,
        ``tuple``, ``range`` …), use it directly: wrapping it here adds an
        indirection layer with no functional benefit, and the source will
        be retained verbatim for the view's lifetime (see Retention below).

    Retention & holdback:
        ``take(n)`` / ``consume(n)`` advance this view's *visible* front
        past the next ``n`` values. A sub-iterator created earlier (via
        slicing or ``iter()``) keeps its own anchor and still observes
        values the parent advanced past; those values are retained
        internally until the last such sub-iterator advances past them
        or is collected.

        Beyond that, lifetime follows the source: a self-draining
        generator releases each value as it yields it, but a source that
        retains its own data (a ``list`` passed in, a generator closing
        over its inputs, …) keeps it alive for as long as
        ``StreamSequence`` holds the source reference.

    Sequence-mixin caveats:
        Inherited from ``collections.abc.Sequence`` and not overridden.
        All of them are correct, but on a one-shot — possibly unbounded —
        view the cost is asymmetric and irreversible:

        - ``__contains__`` / ``index`` stop at the first match. If the
          value is absent, they consume the source to the end.
        - ``count``, ``__reversed__``, and ``len()`` always consume the
          source to the end.

        On an unbounded source these methods hang. Treat the whole group
        like ``list(stream)``: only call them when you know the view is
        bounded and you are willing to materialise it.

    Concurrency:
        Not thread-safe. Concurrent access to a single ``StreamSequence``
        (or to a parent and its sub-iterators) requires external
        synchronisation.

    Type Parameters:
        T: element type produced by the source.
    """

    __slots__ = ('_sourceIterator', '_cache', '_startCacheIndex', '_visibleAbsoluteIndex', '_retainedAbsoluteIndex',
                 '_exhausted', '_liveSubIterators', '__weakref__')

    def __init__(self, iterable: Iterable[T]):
        if not isinstance(iterable, Iterable):
            raise TypeError(f"expected an iterable, got {type(iterable).__name__}")
        # iter() yields a single-pass iterator. _exhausted latches end-of-stream
        # so a one-shot source (file, socket) is never polled past its end.
        self._sourceIterator = iter(iterable)

        # ============================================================
        # Internal state & invariants (hold between public-method calls)
        # ============================================================
        #
        # Source model:
        #     S(i) is the value at absolute index i of the one-shot source;
        #     it yields S(0), S(1), S(2), ... once each, in order.
        #
        # Fields:
        #     _sourceIterator        single-pass iterator over the source
        #     _cache                 buffered values; _cache[:_startCacheIndex]
        #                            are released tombstones (None) awaiting compaction
        #     _startCacheIndex       offset of the live region's front in _cache
        #     _visibleAbsoluteIndex  absolute index of the visible front (self[0])
        #     _retainedAbsoluteIndex absolute index of the first value still in _cache
        #     _exhausted             latched once the source signals end-of-stream
        #     _liveSubIterators      sub-iterators that may still read retained values
        #
        # Coordinate spaces (encoded in field/local naming):
        #     *AbsoluteIndex   absolute source index (the S(i) frame)
        #     *VisibleIndex    position in the visible view: self[k] == S(_visibleAbsoluteIndex + k);
        #                      len(self) == (end-of-stream index) - _visibleAbsoluteIndex
        #     *CacheIndex      position in _cache (also _startCacheIndex)
        #     *Count / n       element counts
        #
        # Cache layout:
        #     The live region _cache[_startCacheIndex:] holds the retained values:
        #         _cache[_startCacheIndex + k] == S(_retainedAbsoluteIndex + k)   for 0 <= k < cachedCount
        #         cachedCount == len(_cache) - _startCacheIndex
        #     Released values are tombstoned (set to None) at once; the dead prefix
        #     _cache[:_startCacheIndex] is physically dropped when it reaches half
        #     the list, keeping reclaim amortised O(1) and _cache bounded.
        #
        # This partitions the source's absolute indices into three regions:
        #     [0, _retainedAbsoluteIndex)                                    pulled, then released — irretrievable
        #     [_retainedAbsoluteIndex, _retainedAbsoluteIndex + cachedCount) held in _cache
        #     [_retainedAbsoluteIndex + cachedCount, +inf)                   not yet pulled
        #
        # Invariants:
        #     (1) 0 <= _retainedAbsoluteIndex <= _visibleAbsoluteIndex
        #     (2) _retainedAbsoluteIndex + cachedCount >= _visibleAbsoluteIndex
        #         (the visible view is always materialisable from _cache)
        #     (3) _retainedAbsoluteIndex <= it._cursorAbsoluteIndex for every live
        #         sub-iterator it (the front never drops a value some sub-iterator
        #         has still to yield); _reclaim restores
        #         _retainedAbsoluteIndex == min(_visibleAbsoluteIndex, *cursors).
        # ============================================================

        self._cache: list[T] = []   # _cache[:_startCacheIndex] are released tombstones (None)
        self._startCacheIndex = 0
        self._visibleAbsoluteIndex = 0
        self._retainedAbsoluteIndex = 0
        self._exhausted = False     # set once the source has signalled end-of-stream
        self._liveSubIterators: weakref.WeakSet[_StreamSequenceIterator[T]] = weakref.WeakSet()

    def _cachedCount(self) -> int:
        """Number of source values currently retained in ``_cache``."""
        return len(self._cache) - self._startCacheIndex

    def _cacheIndexOf(self, absoluteIndex: int) -> int:
        """Physical ``_cache`` index for an absolute source index (>= ``_retainedAbsoluteIndex``)."""
        return self._startCacheIndex + (absoluteIndex - self._retainedAbsoluteIndex)

    def _dropFront(self, n: int) -> None:
        """Release ``n`` leading retained values now, then advance the front
        offset. Tombstoning frees the values immediately (acquire-late /
        release-early contract); the offset avoids the O(N) tail shift a
        ``del _cache[:n]`` would pay. The dead prefix is physically compacted
        once it reaches half the list, keeping it amortised O(1) and bounded.
        """
        newStartCacheIndex = self._startCacheIndex + n
        for i in range(self._startCacheIndex, newStartCacheIndex):
            self._cache[i] = None
        self._startCacheIndex = newStartCacheIndex
        if self._startCacheIndex * 2 >= len(self._cache):
            del self._cache[:self._startCacheIndex]
            self._startCacheIndex = 0

    def __repr__(self) -> str:
        """Debug summary of the buffered state, without pulling data.

        Only already-buffered values are shown; ``...`` flags an unmaterialised tail.
        """
        heldBackCount = self._visibleAbsoluteIndex - self._retainedAbsoluteIndex
        visibleCacheIndex = self._cacheIndexOf(self._visibleAbsoluteIndex)
        bufferedVisibleCount = len(self._cache) - visibleCacheIndex
        previewLimit = 8
        preview = ", ".join(repr(value) for value in self._cache[visibleCacheIndex:visibleCacheIndex + previewLimit])
        if bufferedVisibleCount > previewLimit:
            preview += ", ..."
        return (
            f"<{type(self).__name__} buffered={bufferedVisibleCount} "
            f"heldBack={heldBackCount} subIterators={len(self._liveSubIterators)} "
            f"exhausted={self._exhausted} preview=[{preview}]>"
        )

    def __iter__(self) -> Iterator[T]:
        """Return a fresh iterator over the remaining visible values.

        Anchors on the current visible front; see ``_StreamSequenceIterator``.
        """
        return _StreamSequenceIterator(self)

    def __len__(self) -> int:
        """Return the number of remaining visible values.

        Fully consumes the underlying source; cannot be answered lazily.
        Required by ``collections.abc.Sequence``.
        """
        self._preloadVisibleCount(n=None)
        return (self._retainedAbsoluteIndex + self._cachedCount()) - self._visibleAbsoluteIndex

    def __getitem__(self, key: slice | SupportsIndex) -> "StreamSequence[T] | T":
        """Index or slice the visible view.

        With an integer key, return the value at that visible offset.
        Non-negative indices pull from the source only as far as needed;
        negative indices fully consume the source.

        With a ``slice`` key, return a new ``StreamSequence`` viewing
        the same source through that slice. The returned generator pulls
        from this one lazily; no source values are read until it is
        consumed.

        Required by ``collections.abc.Sequence``.
        """
        if isinstance(key, slice):
            keySlice: slice = key

            iterator = islice_extended(_StreamSequenceIterator(self), keySlice.start, keySlice.stop, keySlice.step)

            # The slice is itself a StreamSequence over the sub-stream. Its
            # wrapped _StreamSequenceIterator anchors on the parent, so the slice
            # stays independent of later parent take()/consume() and buffering.
            return StreamSequence(iterator)

        elif isinstance(key, SupportsIndex):
            keyVisibleIndex = key.__index__()

            if keyVisibleIndex >= 0:
                self._preloadVisibleCount(n=keyVisibleIndex + 1)
                keyCacheIndex = self._cacheIndexOf(self._visibleAbsoluteIndex) + keyVisibleIndex
                return self._cache[keyCacheIndex]
            else:
                self._preloadVisibleCount(n=None)
                # Negative indexing applies to the visible view only; any held-back
                # prefix (pinned by a live sub-iterator) must stay out of reach, so
                # an out-of-range index raises instead of returning a prefix value.
                visibleCacheIndex = self._cacheIndexOf(self._visibleAbsoluteIndex)
                bufferedVisibleCount = len(self._cache) - visibleCacheIndex
                if keyVisibleIndex < -bufferedVisibleCount:
                    raise IndexError("StreamSequence index out of range")
                return self._cache[keyVisibleIndex]
        else:
            raise TypeError(f"indices must be integers or slices, not {type(key).__name__}")

    def _preloadUpTo(self, absoluteEndIndex: int | None) -> None:
        """Ensure ``_cache`` extends up to (but not including) the given absolute
        source-stream index, or fully exhaust the source when
        ``absoluteEndIndex`` is ``None``.

        Lower-level primitive. Preloading shouldn't have any impact on other
        methods' results.
        """
        if self._exhausted:
            return
        if absoluteEndIndex is None:
            toPreloadCount = None    # preload until iterator is exhausted
        else:
            cachedEndAbsoluteIndex = self._retainedAbsoluteIndex + self._cachedCount()
            toPreloadCount = max(0, absoluteEndIndex - cachedEndAbsoluteIndex)
            if toPreloadCount == 0:
                return

        # itertools.islice gracefully stops at end-of-stream when fewer values
        # are available than requested; a short read means the source is spent.
        cacheCountBefore = len(self._cache)
        self._cache.extend(itertools.islice(self._sourceIterator, toPreloadCount))
        if toPreloadCount is None or len(self._cache) - cacheCountBefore < toPreloadCount:
            self._exhausted = True

    def _preloadVisibleCount(self, n: int | None) -> None:
        """Ensure the visible view exposes at least ``n`` values (i.e.
        ``self[0..n-1]`` is reachable, source permitting), or fully exhaust the
        source when ``n`` is ``None``.

        Convenience wrapper over ``_preloadUpTo``.
        """
        if n is None:
            self._preloadUpTo(absoluteEndIndex=None)
        else:
            self._preloadUpTo(absoluteEndIndex=self._visibleAbsoluteIndex + n)

    def _tryGetAtAbsoluteIndex(self, keyAbsoluteIndex: int) -> tuple[bool, T | None]:
        """Read the value at the given absolute source-stream index from the
        cache, without pulling from the source.

        Returns ``(True, value)`` on hit, ``(False, None)`` when the index is
        beyond the cached range (which, after a preload to
        ``keyAbsoluteIndex + 1``, signals end-of-stream).

        Caller is responsible for preloading first if the value may not yet be
        cached.

        Pre: invariant 3 — ``_retainedAbsoluteIndex <= keyAbsoluteIndex``.
        """
        assert keyAbsoluteIndex >= self._retainedAbsoluteIndex
        keyCacheIndex = self._cacheIndexOf(keyAbsoluteIndex)
        if keyCacheIndex >= len(self._cache):
            return False, None
        return True, self._cache[keyCacheIndex]

    def _reclaim(self) -> None:
        """Drop cache entries that no live sub-iterator (and our own visible
        view) can still reach.

        Post-condition::

            _retainedAbsoluteIndex == min(
                _visibleAbsoluteIndex,                                    # used alone when no sub-iterators
                min(it._cursorAbsoluteIndex for it in _liveSubIterators)
            )
        """
        safeFrontAbsoluteIndex = min((self._visibleAbsoluteIndex, *(it._cursorAbsoluteIndex for it in self._liveSubIterators)))
        self._dropFront(safeFrontAbsoluteIndex - self._retainedAbsoluteIndex)
        self._retainedAbsoluteIndex = safeFrontAbsoluteIndex

    def take(self, n: int | None) -> list[T]:
        """Advance the visible front past the next ``n`` values and return them.

        If ``n`` is ``None``, take and return all remaining values. Negative
        ``n`` is clamped to ``0``.

        Consumed values that any live sub-iterator can still reach are
        retained internally; they are released as soon as the last such
        sub-iterator advances past them or is collected.
        """
        return self._advance(n, collect=True)

    def consume(self, n: int | None) -> None:
        """Advance the visible front past the next ``n`` values, discarding them.

        Like :meth:`take` but returns nothing and allocates no list. If ``n``
        is ``None``, consume all remaining values. Negative ``n`` is clamped
        to ``0``.
        """
        self._advance(n, collect=False)

    def _advance(self, n: int | None, *, collect: bool) -> list[T] | None:
        if n is not None:
            n = max(0, n)
        # Live sub-iterators may still read the consumed values, so they must
        # pass through the cache (buffered). Otherwise nothing is held back and
        # we can stream straight past the cache (allocation-free, bounded memory).
        if self._liveSubIterators:
            return self._advanceBuffered(n, collect=collect)
        return self._advanceStreaming(n, collect=collect)

    def _advanceBuffered(self, n: int | None, *, collect: bool) -> list[T] | None:
        """Advance when live sub-iterators may still read the consumed values:
        buffer them in the cache and let ``_reclaim`` trim only what is safe.
        """
        self._preloadVisibleCount(n=n)
        visibleCacheIndex = self._cacheIndexOf(self._visibleAbsoluteIndex)
        availableCount = len(self._cache) - visibleCacheIndex
        consumedCount = availableCount if n is None else min(n, availableCount)
        result = self._cache[visibleCacheIndex:visibleCacheIndex + consumedCount] if collect else None
        self._visibleAbsoluteIndex += consumedCount
        self._reclaim()
        return result

    def _advanceStreaming(self, n: int | None, *, collect: bool) -> list[T] | None:
        """Advance when nothing is held back (``_retainedAbsoluteIndex == _visibleAbsoluteIndex``):
        serve the cached prefix, then pull the remainder straight from the source
        without materialising it in the cache.
        """
        assert self._retainedAbsoluteIndex == self._visibleAbsoluteIndex
        # 1. Cached values at the visible front.
        cachedCount = self._cachedCount()
        fromCacheCount = cachedCount if n is None else min(n, cachedCount)
        startCacheIndex = self._startCacheIndex
        result: list[T] | None = self._cache[startCacheIndex:startCacheIndex + fromCacheCount] if collect else None
        self._dropFront(fromCacheCount)      # release served values now; offset-based, no tail shift

        # 2. Remainder, streamed straight from the source.
        remainingCount = None if n is None else n - fromCacheCount
        fromSourceCount = 0
        if (remainingCount is None or remainingCount > 0) and not self._exhausted:
            stream = itertools.islice(self._sourceIterator, remainingCount)
            if collect:
                result.extend(stream)
                fromSourceCount = len(result) - fromCacheCount
            else:
                # Drain without retaining the values.
                fromSourceCount = sum(1 for _ in stream)
            if remainingCount is None or fromSourceCount < remainingCount:
                self._exhausted = True

        self._visibleAbsoluteIndex += fromCacheCount + fromSourceCount
        self._retainedAbsoluteIndex = self._visibleAbsoluteIndex
        return result
