"""A generic, minimal name-to-instance registry.

Shared by `EngineManager` (driver name -> `Engine`) and the ORM adapter
registry (framework name -> `SearchableAdapter`) so both resolve, cache, and
extend the same way instead of each reimplementing it.
"""

from __future__ import annotations

from typing import Callable, Generic, TypeVar

T = TypeVar("T")


class Registry(Generic[T]):
    """Resolves names to lazily-built, cached instances of `T`."""

    def __init__(self) -> None:
        self._factories: dict[str, Callable[[], T]] = {}
        self._instances: dict[str, T] = {}

    def register(self, name: str, factory: Callable[[], T]) -> None:
        """Register (or replace) the factory used to build `name`.

        Replacing a factory drops any cached instance for that name so the
        next `resolve()` rebuilds it.
        """
        self._factories[name] = factory
        self._instances.pop(name, None)

    def resolve(self, name: str) -> T:
        """Return the cached instance for `name`, building it on first use.

        Raises:
            KeyError: if no factory is registered under `name`.
        """
        if name not in self._instances:
            if name not in self._factories:
                raise KeyError(name)
            self._instances[name] = self._factories[name]()
        return self._instances[name]

    def available(self) -> list[str]:
        """Return the sorted names of every registered factory."""
        return sorted(self._factories)

    def forget(self, name: str | None = None) -> None:
        """Drop cached instance(s) so the next `resolve()` rebuilds them.

        Args:
            name: Drop only this name's cached instance; drop everything
                cached when omitted.
        """
        if name is None:
            self._instances.clear()
        else:
            self._instances.pop(name, None)
