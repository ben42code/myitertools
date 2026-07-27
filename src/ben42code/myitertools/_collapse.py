"""
collapse — lazily flatten nested iterables, with per-type customisation.

Walks a nested iterable and yields its leaves depth-first, pulling from the
source only as far as the consumer requests. A ``handlers`` mapping lets you
replace elements of a given type with a custom iterable (which is itself
flattened), and ``atoms`` marks types that should be yielded whole instead of
being iterated into.

Uses an explicit stack rather than recursion, so arbitrarily deep nesting
cannot raise ``RecursionError``.
"""
from typing import Any, Callable, Iterable, Iterator, Mapping, Optional, TypeAlias

__all__ = ["collapse"]

Handler: TypeAlias = Callable[[Any], Iterable]
Handlers: TypeAlias = Mapping[type, Handler]


def collapse(
    iterable: Iterable,
    *,
    handlers: Optional[Handlers] = None,
    atoms: tuple[type, ...] = (str, bytes),
) -> Iterator:
    """
    Lazily flatten ``iterable``, yielding its leaves depth-first.

    ``handlers`` maps a type to a function: an element matching that type is
    replaced by ``handler(element)``, and the result is flattened in turn — so
    it is re-matched against ``handlers`` and ``atoms`` as well. Handlers take
    precedence over ``atoms``.

    ``atoms`` lists types yielded whole rather than iterated into (default
    ``(str, bytes)`` so plain text is not exploded into characters). Any element
    that is neither handled, an atom, nor iterable is yielded as a leaf.
    """
    handlers = handlers or {}

    # Explicit iterator stack: descend by pushing a child iterator, ascend by
    # popping an exhausted one. A partially consumed parent iterator resumes
    # where it left off, so depth is bounded by the stack, not the call frames.
    stack: list[Iterator] = [iter(iterable)]
    while stack:
        for element in stack[-1]:
            handler = _match(element, handlers)
            if handler is not None:
                # Re-feed the result as a single element so it is flattened and
                # re-matched against handlers (a returned str hits a str handler
                # again rather than being exploded into characters).
                stack.append(iter((handler(element),)))
                break
            if isinstance(element, atoms) or not isinstance(element, Iterable):
                yield element
            else:
                stack.append(iter(element))
                break
        else:
            stack.pop()


def _match(
    element: Any,
    handlers: Handlers,
) -> Optional[Handler]:
    for type_, handler in handlers.items():
        if isinstance(element, type_):
            return handler
    return None
