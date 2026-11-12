"""Decorator-based plug-in registry.

A ``Registry`` maps a short name (e.g. ``"price"``) to a class. Classes add
themselves with a decorator at definition time::

    CRITERIA = Registry("criterion", Criterion)

    @CRITERIA.register("price")
    class PriceCriterion(Criterion):
        ...

The ranking and filtering engines then look classes up by the names used in
configuration files (weights, profiles), so adding a new criterion or
constraint means writing one decorated class, with no edits to the engine.
"""

from collections.abc import Callable, Iterator
from typing import Any, Generic, TypeVar

from busbidder.exceptions import RegistryError

T = TypeVar("T")


class Registry(Generic[T]):
    """A named collection of subclasses of ``base``."""

    def __init__(self, kind: str, base: type[T]) -> None:
        self.kind = kind
        self._base = base
        self._entries: dict[str, type[T]] = {}

    def register(self, name: str) -> Callable[[type[T]], type[T]]:
        """Return a class decorator that registers the class under ``name``.

        The decorator also stores ``name`` on the class as ``cls.name`` so the
        registry key is the single source of truth for the plug-in's name.
        """
        if not name.isidentifier():
            raise RegistryError(f"invalid {self.kind} name {name!r}: must be a Python identifier")

        def decorator(cls: type[T]) -> type[T]:
            if not (isinstance(cls, type) and issubclass(cls, self._base)):
                raise RegistryError(
                    f"cannot register {cls!r} as {self.kind}: not a subclass of {self._base.__name__}"
                )
            if name in self._entries:
                raise RegistryError(
                    f"duplicate {self.kind} name {name!r} "
                    f"(already used by {self._entries[name].__name__})"
                )
            cls.name = name  # type: ignore[attr-defined]
            self._entries[name] = cls
            return cls

        return decorator

    def get(self, name: str) -> type[T]:
        """Return the class registered under ``name``."""
        try:
            return self._entries[name]
        except KeyError:
            known = ", ".join(self.names()) or "none"
            raise RegistryError(f"unknown {self.kind} {name!r} (known: {known})") from None

    def create(self, name: str, *args: Any, **kwargs: Any) -> T:
        """Instantiate the class registered under ``name``."""
        return self.get(name)(*args, **kwargs)

    def names(self) -> list[str]:
        """Registered names in registration order (the order the classes are defined)."""
        return list(self._entries)

    def __contains__(self, name: object) -> bool:
        return name in self._entries

    def __iter__(self) -> Iterator[str]:
        return iter(self.names())

    def __len__(self) -> int:
        return len(self._entries)
