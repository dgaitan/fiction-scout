"""The Engine contract every search driver must implement."""

from __future__ import annotations

import abc
from typing import TYPE_CHECKING, Any

from fiction_scout.exceptions import IndexSettingsNotSupportedError

if TYPE_CHECKING:
    from fiction_scout.protocols import SearchableAdapter
    from fiction_scout.search.builder import Builder


class Page:
    """One page of paginated search results."""

    def __init__(
        self, items: list[Any], *, total: int, page: int, per_page: int
    ) -> None:
        self.items = items
        self.total = total
        self.page = page
        self.per_page = per_page

    @property
    def has_more(self) -> bool:
        """Whether pages after this one exist."""
        return self.page * self.per_page < self.total

    def __len__(self) -> int:
        return len(self.items)

    def __iter__(self) -> Any:
        return iter(self.items)


class Engine(abc.ABC):
    """Base class for every fiction-scout search driver.

    Mirrors Laravel Scout's `Engine` contract: eight required methods plus
    optional index-management hooks. A new driver extends this class and
    registers itself with `EngineManager.extend()` — no core code changes
    required. See `docs/extending/custom-drivers.md`.
    """

    @abc.abstractmethod
    def update(self, models: list[Any], adapter: SearchableAdapter) -> None:
        """Add or update `models` in the index."""

    @abc.abstractmethod
    def delete(self, models: list[Any], adapter: SearchableAdapter) -> None:
        """Remove `models` from the index."""

    @abc.abstractmethod
    def flush(self, model: type, adapter: SearchableAdapter) -> None:
        """Remove every record of `model` from the index."""

    @abc.abstractmethod
    def search(self, builder: Builder) -> Any:
        """Execute `builder` and return raw, engine-specific results."""

    @abc.abstractmethod
    def paginate(self, builder: Builder, per_page: int, page: int) -> Page:
        """Execute `builder` and return one page of matching model instances."""

    @abc.abstractmethod
    def map_ids(self, results: Any) -> list[Any]:
        """Extract the ordered list of scout keys from raw `results`."""

    @abc.abstractmethod
    def map(self, builder: Builder, results: Any, model: type) -> list[Any]:
        """Convert raw `results` into a list of `model` instances."""

    @abc.abstractmethod
    def get_total_count(self, results: Any) -> int:
        """Extract the total match count from raw `results`."""

    def index_name_for(self, model: type, adapter: SearchableAdapter) -> str:
        """Resolve the final index/table name `model` reads and writes to.

        Default is a passthrough to `adapter.searchable_as(model)` — correct
        for `DatabaseEngine`/`CollectionEngine`, which query a real DB table
        and must never see it prefixed. External-index drivers (Algolia,
        Meilisearch) override this to prepend `FictionScoutConfig.index_prefix`,
        mirroring Laravel Scout's `scout.prefix`.
        """
        return adapter.searchable_as(model)

    def create_index(self, name: str, **options: Any) -> None:  # noqa: B027
        """Create an index named `name`. No-op unless a driver overrides it."""

    def delete_index(self, name: str) -> None:  # noqa: B027
        """Delete the index named `name`. No-op unless a driver overrides it."""

    def update_index_settings(
        self, model: type, adapter: SearchableAdapter, **settings: Any
    ) -> None:
        """Apply this driver's index settings for `model`.

        Covers things like searchable attributes and ranking rules.
        Raises `IndexSettingsNotSupportedError` by default — unlike
        `create_index`/`delete_index`, this must never silently no-op, since
        the CLI's `sync-index-settings` command relies on the raise to tell a
        caller their driver has nothing to apply. Override in drivers with a
        real settings API (e.g. Meilisearch).
        """
        raise IndexSettingsNotSupportedError(type(self).__name__)

    def keys(self, builder: Builder) -> list[Any]:
        """Return the scout keys matching `builder`, without fetching models."""
        return self.map_ids(self.search(builder))

    def get(self, builder: Builder) -> list[Any]:
        """Execute `builder` and return the matching model instances."""
        results = self.search(builder)
        return self.map(builder, results, builder.model)
