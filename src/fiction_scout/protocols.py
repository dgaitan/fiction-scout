"""Structural interfaces that decouple core fiction-scout code from any ORM.

Engines, the search `Builder`, and the CLI only ever call methods on
`SearchableAdapter` — never on Django or SQLAlchemy directly. This is the
seam that makes a new ORM adapter a pure-addition change: see
`docs/extending/custom-adapters.md`.
"""

from __future__ import annotations

from typing import Any, Callable, Iterator, Protocol, Sequence, runtime_checkable


@runtime_checkable
class SearchableAdapter(Protocol):
    """Translates between a specific ORM's models and fiction-scout's core.

    One instance of a concrete adapter (e.g. `DjangoAdapter`,
    `SQLAlchemyAdapter`) is shared by every searchable model registered with
    that framework; adapter methods are always passed the `model` or
    `instance` they should act on.
    """

    def searchable_as(self, model: type) -> str:
        """Return the index/table name `model`'s records are stored under."""
        ...

    def get_scout_key(self, instance: Any) -> Any:
        """Return the unique key identifying `instance` in the search index."""
        ...

    def get_scout_key_name(self, model: type) -> str:
        """Return the field name backing `get_scout_key` for `model`."""
        ...

    def to_searchable_array(self, instance: Any) -> dict[str, Any]:
        """Return the dict of data persisted to the search index for `instance`."""
        ...

    def chunk_records(self, model: type, *, chunk_size: int) -> Iterator[list[Any]]:
        """Yield every record of `model`, `chunk_size` at a time."""
        ...

    def fetch_by_ids(self, model: type, ids: Sequence[Any]) -> list[Any]:
        """Fetch `model` instances whose scout key is in `ids`, any order."""
        ...

    def is_soft_deleted(self, instance: Any) -> bool:
        """Return whether `instance` is currently soft-deleted."""
        ...

    def soft_delete_enabled(self, model: type) -> bool:
        """Return whether `model` participates in soft-delete tracking."""
        ...

    # -- Query-building surface, used only by the database engine. -------
    # Each method takes and returns an opaque, adapter-specific query object
    # (a Django `QuerySet`, a SQLAlchemy `Select`, ...); `DatabaseEngine`
    # never inspects it, only threads it through these calls.

    def query_all(self, model: type) -> Any:
        """Return a fresh, unfiltered query for every record of `model`."""
        ...

    def apply_search_term(self, query: Any, model: type, term: str) -> Any:
        """Return `query` filtered to records matching `term`.

        Implementations decide, per searchable column, whether to match via
        `LIKE '%term%'`, a full-text index, or a `term%` prefix — based on
        the `search_using_full_text`/`search_using_prefix` decorators from
        `fiction_scout.strategies` applied to the model's
        `to_searchable_array` method. Columns with no decorator default to
        `LIKE`.
        """
        ...

    def apply_where(self, query: Any, field: str, value: Any) -> Any:
        """Return `query` additionally constrained to `field == value`."""
        ...

    def apply_where_in(self, query: Any, field: str, values: Sequence[Any]) -> Any:
        """Return `query` additionally constrained to `field` in `values`."""
        ...

    def apply_where_not_in(self, query: Any, field: str, values: Sequence[Any]) -> Any:
        """Return `query` additionally constrained to `field` not in `values`."""
        ...

    def apply_trashed_filter(
        self, query: Any, model: type, *, with_trashed: bool, only_trashed: bool
    ) -> Any:
        """Return `query` filtered for soft-deleted records per the given flags.

        A no-op when `model` doesn't have soft-delete enabled. When it does:
        excludes soft-deleted records by default, includes them alongside
        live records when `with_trashed=True`, or returns only soft-deleted
        records when `only_trashed=True`.
        """
        ...

    def execute_query(self, query: Any) -> list[Any]:
        """Execute `query` and return the matching model instances."""
        ...

    def count_query(self, query: Any) -> int:
        """Return the number of records `query` matches, without fetching them."""
        ...

    def paginate_query(self, query: Any, *, per_page: int, page: int) -> list[Any]:
        """Execute `query` and return only the records on the given page."""
        ...


@runtime_checkable
class Dispatcher(Protocol):
    """Executes indexing work either immediately or via a background queue."""

    def dispatch(self, fn: Callable[[], None]) -> None:
        """Run `fn`, either synchronously or by handing it to a queue."""
        ...
