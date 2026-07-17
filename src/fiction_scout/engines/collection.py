"""In-memory search engine for prototypes, tests, and tiny datasets."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from fiction_scout.engines.base import Engine, Page

if TYPE_CHECKING:
    from fiction_scout.protocols import SearchableAdapter
    from fiction_scout.search.builder import Builder

_SCOUT_KEY_FIELD = "_scout_key"


class CollectionEngine(Engine):
    """Filters every record of a model in Python on each search.

    Mirrors Scout's "collection" engine: no indexing step, no external
    service, no database-specific features required — just not efficient
    enough for anything beyond prototypes, tests, or a few hundred records.
    """

    def update(self, models: list[Any], adapter: SearchableAdapter) -> None:
        """No-op: this engine always reads live data: nothing to sync."""

    def delete(self, models: list[Any], adapter: SearchableAdapter) -> None:
        """No-op: this engine always reads live data: nothing to sync."""

    def flush(self, model: type, adapter: SearchableAdapter) -> None:
        """No-op: there is no index to flush."""

    def search(self, builder: Builder) -> list[dict[str, Any]]:
        """Return every searchable-array dict matching `builder`'s constraints."""
        adapter = builder.adapter
        matches: list[dict[str, Any]] = []
        for chunk in adapter.chunk_records(builder.model, chunk_size=500):
            for instance in chunk:
                if not self._passes_trashed_filter(instance, builder, adapter):
                    continue
                array = adapter.to_searchable_array(instance)
                if not self._matches_constraints(array, builder):
                    continue
                matches.append(
                    {**array, _SCOUT_KEY_FIELD: adapter.get_scout_key(instance)}
                )
        return matches

    @staticmethod
    def _passes_trashed_filter(
        instance: Any, builder: Builder, adapter: SearchableAdapter
    ) -> bool:
        deleted = adapter.is_soft_deleted(instance)
        if builder.only_trashed_:
            return deleted
        if builder.with_trashed_:
            return True
        return not deleted

    def _matches_constraints(self, array: dict[str, Any], builder: Builder) -> bool:
        if builder.term and not self._contains_query(array, builder.term):
            return False
        for field, value in builder.wheres.items():
            if array.get(field) != value:
                return False
        for field, values in builder.where_ins.items():
            if array.get(field) not in values:
                return False
        for field, values in builder.where_not_ins.items():
            if array.get(field) in values:
                return False
        return True

    @staticmethod
    def _contains_query(array: dict[str, Any], query: str) -> bool:
        needle = query.lower()
        return any(needle in str(value).lower() for value in array.values())

    def paginate(self, builder: Builder, per_page: int, page: int) -> Page:
        """Return one page of matching results."""
        results = self.search(builder)
        start = (page - 1) * per_page
        page_slice = results[start : start + per_page]
        return Page(
            self.map(builder, page_slice, builder.model),
            total=len(results),
            page=page,
            per_page=per_page,
        )

    def map_ids(self, results: list[dict[str, Any]]) -> list[Any]:
        """Extract scout keys from `search()`'s results, in order."""
        return [record[_SCOUT_KEY_FIELD] for record in results]

    def map(
        self, builder: Builder, results: list[dict[str, Any]], model: type
    ) -> list[Any]:
        """Fetch and return model instances for `results`, preserving match order."""
        adapter = builder.adapter
        ids = self.map_ids(results)
        instances = adapter.fetch_by_ids(model, ids)
        by_key = {adapter.get_scout_key(instance): instance for instance in instances}
        return [by_key[key] for key in ids if key in by_key]

    def get_total_count(self, results: list[dict[str, Any]]) -> int:
        """Return the number of matching records."""
        return len(results)
