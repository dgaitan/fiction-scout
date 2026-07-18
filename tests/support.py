"""Plain-Python test doubles: a model and a `SearchableAdapter` implementation.

These exercise the same contract a real Django/SQLAlchemy adapter would,
without either dependency — this is what proves core engine logic (the
collection engine's filtering, the database engine's query dispatch) is
correct independent of any ORM.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field
from typing import Any, Callable

from fiction_scout.engines.base import Engine, Page
from fiction_scout.strategies import SearchStrategy, get_column_strategies


@dataclass
class Article:
    """A plain-Python stand-in for an ORM model."""

    id: int
    title: str
    body: str
    deleted_at: str | None = None

    def to_searchable_array(self) -> dict[str, Any]:
        """Return the default (undecorated) searchable field set."""
        return {"id": self.id, "title": self.title, "body": self.body}


class FakeAdapter:
    """A minimal `SearchableAdapter` implementation backed by an in-memory list."""

    def __init__(self, records: list[Any]) -> None:
        self.records = records

    def searchable_as(self, model: type) -> str:
        return "articles"

    def get_scout_key(self, instance: Any) -> Any:
        return instance.id

    def get_scout_key_name(self, model: type) -> str:
        return "id"

    def to_searchable_array(self, instance: Any) -> dict[str, Any]:
        return instance.to_searchable_array()

    def chunk_records(self, model: type, *, chunk_size: int) -> Iterator[list[Any]]:
        for start in range(0, len(self.records), chunk_size):
            yield self.records[start : start + chunk_size]

    def fetch_by_ids(self, model: type, ids: Sequence[Any]) -> list[Any]:
        # Compares by str() so ids that arrive as strings (e.g. from an
        # external search index's document ids) still match integer
        # `record.id` values, the same way a real ORM's `pk__in` lookup
        # coerces a string id against an integer primary key column.
        wanted = {str(i) for i in ids}
        return [record for record in self.records if str(record.id) in wanted]

    def is_soft_deleted(self, instance: Any) -> bool:
        return instance.deleted_at is not None

    def soft_delete_enabled(self, model: type) -> bool:
        return True

    # -- query-building surface (used by DatabaseEngine) ------------------

    def query_all(self, model: type) -> list[Any]:
        return list(self.records)

    def apply_search_term(self, query: list[Any], model: type, term: str) -> list[Any]:
        strategies = get_column_strategies(model.to_searchable_array)
        needle = term.lower()

        def matches(instance: Any) -> bool:
            for field_name, value in instance.to_searchable_array().items():
                strategy = strategies.get(field_name, SearchStrategy.LIKE)
                text = str(value).lower()
                if strategy is SearchStrategy.PREFIX:
                    if text.startswith(needle):
                        return True
                elif needle in text:
                    return True
            return False

        return [instance for instance in query if matches(instance)]

    def apply_where(self, query: list[Any], field: str, value: Any) -> list[Any]:
        return [instance for instance in query if getattr(instance, field) == value]

    def apply_where_in(
        self, query: list[Any], field: str, values: Sequence[Any]
    ) -> list[Any]:
        return [instance for instance in query if getattr(instance, field) in values]

    def apply_where_not_in(
        self, query: list[Any], field: str, values: Sequence[Any]
    ) -> list[Any]:
        return [
            instance for instance in query if getattr(instance, field) not in values
        ]

    def apply_trashed_filter(
        self, query: list[Any], model: type, *, with_trashed: bool, only_trashed: bool
    ) -> list[Any]:
        if only_trashed:
            return [instance for instance in query if instance.deleted_at is not None]
        if with_trashed:
            return list(query)
        return [instance for instance in query if instance.deleted_at is None]

    def execute_query(self, query: list[Any]) -> list[Any]:
        return list(query)

    def count_query(self, query: list[Any]) -> int:
        return len(query)

    def paginate_query(
        self, query: list[Any], *, per_page: int, page: int
    ) -> list[Any]:
        start = (page - 1) * per_page
        return query[start : start + per_page]


@dataclass
class SpyEngine(Engine):
    """Records `update`/`delete` calls instead of touching a real index."""

    updated_batches: list[list[Any]] = field(default_factory=list)
    deleted_batches: list[list[Any]] = field(default_factory=list)
    flushed: list[type] = field(default_factory=list)

    def update(self, models: list[Any], adapter: Any) -> None:
        self.updated_batches.append(list(models))

    def delete(self, models: list[Any], adapter: Any) -> None:
        self.deleted_batches.append(list(models))

    def flush(self, model: type, adapter: Any) -> None:
        self.flushed.append(model)

    def search(self, builder: Any) -> Any:
        return []

    def paginate(self, builder: Any, per_page: int, page: int) -> Page:
        return Page([], total=0, page=page, per_page=per_page)

    def map_ids(self, results: Any) -> list[Any]:
        return []

    def map(self, builder: Any, results: Any, model: type) -> list[Any]:
        return []

    def get_total_count(self, results: Any) -> int:
        return 0


@dataclass
class SpyDispatcher:
    """Records dispatched calls, then runs them immediately."""

    dispatched_count: int = 0

    def dispatch(self, fn: Callable[[], None]) -> None:
        self.dispatched_count += 1
        fn()


@dataclass
class AlgoliaHit:
    """A single result row as `AlgoliaEngine` expects to read it off a response."""

    object_id: str


@dataclass
class AlgoliaSearchResponse:
    hits: list[AlgoliaHit]
    nb_hits: int


class FakeAlgoliaClient:
    """A hand-rolled fake standing in for `algoliasearch`'s `SearchClientSync`.

    Matches this project's existing test-double style (`SpyEngine`,
    `FakeAdapter`) rather than `unittest.mock`. Shared by
    `tests/test_algolia/` (engine-level tests against `FakeAdapter`) and
    `tests/test_django/` (integration tests against the real
    `DjangoAdapter`) so both exercise `AlgoliaEngine` against the identical
    fake wire boundary — see the design-decision docstring in
    `engines/algolia.py`.
    """

    def __init__(
        self, *, search_hits: list[AlgoliaHit] | None = None, nb_hits: int = 0
    ) -> None:
        self.saved: list[tuple[str, list[dict[str, Any]]]] = []
        self.deleted: list[tuple[str, list[str]]] = []
        self.cleared: list[str] = []
        self.deleted_indexes: list[str] = []
        self.search_calls: list[tuple[str, dict[str, Any]]] = []
        self._search_hits = search_hits or []
        self._nb_hits = nb_hits

    def set_search_response(self, *, hits: list[AlgoliaHit], nb_hits: int) -> None:
        """Configure what the next `search_single_index` call returns."""
        self._search_hits = hits
        self._nb_hits = nb_hits

    def save_objects(self, *, index_name: str, objects: list[dict[str, Any]]) -> None:
        self.saved.append((index_name, list(objects)))

    def delete_objects(self, *, index_name: str, object_ids: list[str]) -> None:
        self.deleted.append((index_name, list(object_ids)))

    def clear_objects(self, *, index_name: str) -> None:
        self.cleared.append(index_name)

    def delete_index(self, *, index_name: str) -> None:
        self.deleted_indexes.append(index_name)

    def search_single_index(
        self, *, index_name: str, search_params: dict[str, Any]
    ) -> AlgoliaSearchResponse:
        self.search_calls.append((index_name, dict(search_params)))
        return AlgoliaSearchResponse(hits=self._search_hits, nb_hits=self._nb_hits)
