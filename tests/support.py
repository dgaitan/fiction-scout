"""Plain-Python test doubles: a model and a `SearchableAdapter` implementation.

These exercise the same contract a real Django/SQLAlchemy adapter would,
without either dependency — this is what proves core engine logic (the
collection engine's filtering, the database engine's query dispatch) is
correct independent of any ORM.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterator, Sequence

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
        wanted = set(ids)
        return [record for record in self.records if record.id in wanted]

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

    def apply_where_in(self, query: list[Any], field: str, values: Sequence[Any]) -> list[Any]:
        return [instance for instance in query if getattr(instance, field) in values]

    def apply_where_not_in(self, query: list[Any], field: str, values: Sequence[Any]) -> list[Any]:
        return [instance for instance in query if getattr(instance, field) not in values]

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

    def paginate_query(self, query: list[Any], *, per_page: int, page: int) -> list[Any]:
        start = (page - 1) * per_page
        return query[start : start + per_page]
