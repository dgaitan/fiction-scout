"""Resolves driver names to `Engine` instances, with dependency validation."""

from __future__ import annotations

from typing import Callable

from fiction_scout.config import FictionScoutConfig
from fiction_scout.dependencies import require_installed
from fiction_scout.engines.base import Engine
from fiction_scout.exceptions import UnknownDriverError
from fiction_scout.registry import Registry

# driver name -> (importable module to check for, pip extra to suggest).
# Drivers with no external dependency (database, collection) aren't listed.
_DRIVER_DEPENDENCIES: dict[str, tuple[str, str]] = {}


class EngineManager:
    """Resolves and caches `Engine` instances by driver name.

    Built-in drivers (`database`, `collection`) are registered at
    construction time. Call `.extend(name, factory)` to register additional
    drivers — custom or third-party — without modifying this class. See
    `docs/extending/custom-drivers.md`.
    """

    def __init__(self, config: FictionScoutConfig | None = None) -> None:
        self._config = config or FictionScoutConfig()
        self._registry: Registry[Engine] = Registry()
        self._register_builtin_drivers()

    @property
    def config(self) -> FictionScoutConfig:
        return self._config

    def _register_builtin_drivers(self) -> None:
        from fiction_scout.engines.collection import CollectionEngine
        from fiction_scout.engines.database import DatabaseEngine

        self._registry.register("collection", CollectionEngine)
        self._registry.register("database", DatabaseEngine)

    def extend(self, name: str, factory: Callable[[], Engine]) -> None:
        """Register `factory` as the driver named `name`.

        The extension point for custom or third-party engines (Algolia,
        Meilisearch, Typesense, or anything else). To also validate that
        driver's dependency, add it to the caller's own dependency table and
        call `require_installed` directly, or wrap `factory` to do so.
        """
        self._registry.register(name, factory)

    def validate_dependency(self, name: str) -> None:
        """Raise `MissingDependencyError` if driver `name`'s SDK isn't installed.

        No-op for drivers with no external dependency, or drivers not
        present in the dependency table at all.
        """
        dependency = _DRIVER_DEPENDENCIES.get(name)
        if dependency is None:
            return
        module_name, extra = dependency
        require_installed(feature=name, module_name=module_name, extra=extra)

    def driver(self, name: str | None = None) -> Engine:
        """Return the `Engine` instance for `name`, or the configured default."""
        resolved_name = name or self._config.driver
        self.validate_dependency(resolved_name)
        try:
            return self._registry.resolve(resolved_name)
        except KeyError:
            raise UnknownDriverError(
                resolved_name, self._registry.available()
            ) from None

    def forget_engines(self) -> None:
        """Drop all cached engine instances so the next `.driver()` rebuilds them."""
        self._registry.forget()
