"""
collapse — lazily flatten nested iterables, with per-type customisation.

Walks a nested iterable and yields its leaves depth-first, pulling from the
source only as far as the consumer requests. A ``handlers`` mapping lets you
replace elements of a given type with a custom iterable (which is itself
flattened), and ``atoms`` marks types that should be yielded whole instead of
being iterated into.

A type may be registered as an atom or as a handler, but not both. Which rule
applies to an element is decided by type specificity (the most-derived matching
type wins, honouring abstract base classes), not by declaration order, using
``functools.singledispatch``.

Uses an explicit stack rather than recursion, so arbitrarily deep nesting
cannot raise ``RecursionError``.
"""
from enum import Enum, auto
from functools import singledispatch
from typing import Any, Callable, Iterable, Iterator, Mapping, NamedTuple, Optional, TypeAlias

__all__ = ["collapse"]

Handler: TypeAlias = Callable[[Any], Iterable]
Handlers: TypeAlias = Mapping[type, Handler]
Atoms: TypeAlias = tuple[type, ...]

_DEFAULT_ATOMS: Atoms = (str, bytes)


class _Action(Enum):
    ATOM = auto()       # yield the element whole
    HANDLER = auto()    # replace the element via the handler, then re-flatten
    DEFAULT = auto()    # descend if iterable, otherwise yield as a leaf


class _Resolution(NamedTuple):
    action: _Action
    handler: Optional[Handler]


def collapse(
    iterable: Iterable,
    *,
    handlers: Optional[Handlers] = None,
    atoms: Optional[Atoms] = None,
) -> Iterator:
    """
    Lazily flatten ``iterable``, yielding its leaves depth-first.

    ``handlers`` maps a type to a function: an element matching that type is
    replaced by ``handler(element)``, and the result is flattened in turn — so
    it is re-resolved against ``handlers`` and ``atoms`` as well.

    ``atoms`` lists types yielded whole rather than iterated into. When omitted
    it defaults to ``(str, bytes)`` so plain text is not exploded into
    characters; pass an explicit tuple (e.g. ``()``) to override. Any element
    that is neither handled, an atom, nor iterable is yielded as a leaf.

    A type cannot be both an atom and a handler: overlapping an explicit
    ``atoms`` entry with a handler raises ``ValueError`` (overriding a default
    atom with a handler is allowed). When an element's type matches several
    unrelated registered types (e.g. two abstract base classes), resolution is
    ambiguous and raises ``ValueError``.
    """
    resolve = _build_resolver(handlers, atoms)
    return _flatten(iterable, resolve)


def _flatten(iterable: Iterable, resolve: Callable[[Any], _Resolution]) -> Iterator:
    # Explicit iterator stack: descend by pushing a child iterator, ascend by
    # popping an exhausted one. A partially consumed parent iterator resumes
    # where it left off, so depth is bounded by the stack, not the call frames.
    stack: list[Iterator] = [iter(iterable)]
    while stack:
        for element in stack[-1]:
            try:
                resolution = resolve(element)
            except RuntimeError as error:
                raise ValueError(
                    f"collapse: ambiguous type resolution for "
                    f"{type(element).__name__!r}: {error}"
                ) from error
            match resolution.action:
                case _Action.ATOM:
                    yield element
                case _Action.HANDLER:
                    # Re-feed the result as a single element so it is flattened
                    # and re-resolved (a returned str hits a str handler again
                    # rather than being exploded into characters).
                    stack.append(iter((resolution.handler(element),)))
                    break
                case _Action.DEFAULT:
                    if isinstance(element, Iterable):
                        stack.append(iter(element))
                        break
                    yield element
                # Defensive: every _Action member is handled above; this guards
                # against a future member being added without a case.
                case _:  # pragma: no cover
                    raise AssertionError(f"unhandled action: {resolution.action}")
        else:
            stack.pop()


def _build_resolver(
    handlers: Optional[Handlers],
    atoms: Optional[Atoms],
) -> Callable[[Any], _Resolution]:
    handlers = handlers or {}
    handler_types = set(handlers)

    if atoms is None:
        # Default atoms yield to a handler registered for the same type.
        atoms = tuple(t for t in _DEFAULT_ATOMS if t not in handler_types)
    else:
        atoms = tuple(atoms)
        conflicting = handler_types.intersection(atoms)
        if conflicting:
            names = ", ".join(sorted(t.__name__ for t in conflicting))
            raise ValueError(
                f"collapse: {names} cannot be both an atom and a handler type"
            )

    @singledispatch
    def resolve(element: Any) -> _Resolution:
        return _Resolution(_Action.DEFAULT, None)

    for atom_type in atoms:
        resolve.register(atom_type, _atom_action)
    for handler_type, handler in handlers.items():
        resolve.register(handler_type, _handler_action(handler))

    return resolve


def _atom_action(element: Any) -> _Resolution:
    return _Resolution(_Action.ATOM, None)


def _handler_action(handler: Handler) -> Callable[[Any], _Resolution]:
    def resolve_to_handler(element: Any) -> _Resolution:
        return _Resolution(_Action.HANDLER, handler)
    return resolve_to_handler
