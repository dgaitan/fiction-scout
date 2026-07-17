"""Database engine: searches a model's existing table directly.

No separate indexing step — results always reflect current database state.
Mirrors Scout's "database" engine: `LIKE` queries by default, with per-column
full-text/prefix strategies available via the decorators in
`fiction_scout.strategies`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from fiction_scout.engines.base import Engine, Page

if TYPE_CHECKING:
    from fiction_scout.protocols import SearchableAdapter
    from fiction_scout.search.builder import Builder


@dataclass
class _DatabaseSearchResult:
    """This engine's raw result: a built, not-yet-executed query plus the
    adapter needed to run it — `map`/`map_ids`/`get_total_count` all receive
    this and unpack it, since a bare query object alone can't run itself.
    """

    query: Any
    adapter: SearchableAdapter


class DatabaseEngine(Engine):
    """Searches a model's existing database table directly."""

    def update(self, models: list[Any], adapter: SearchableAdapter) -> None:
        """No-op: this engine always reads live data, nothing to sync."""

    def delete(self, models: list[Any], adapter: SearchableAdapter) -> None:
        """No-op: this engine always reads live data, nothing to sync."""

    def flush(self, model: type, adapter: SearchableAdapter) -> None:
        """No-op: there is no index to flush."""

    def _build_query(self, builder: Builder) -> Any:
        adapter = builder.adapter
        query = adapter.query_all(builder.model)
        if builder.query:
            query = adapter.apply_search_term(query, builder.model, builder.query)
        for field, value in builder.wheres.items():
            query = adapter.apply_where(query, field, value)
        for field, values in builder.where_ins.items():
            query = adapter.apply_where_in(query, field, values)
        for field, values in builder.where_not_ins.items():
            query = adapter.apply_where_not_in(query, field, values)
        query = adapter.apply_trashed_filter(
            query,
            builder.model,
            with_trashed=builder.with_trashed_,
            only_trashed=builder.only_trashed_,
        )
        if builder.query_callback is not None:
            query = builder.query_callback(query)
        return query

    def search(self, builder: Builder) -> _DatabaseSearchResult:
        """Build (but do not execute) the query for `builder`'s constraints."""
        return _DatabaseSearchResult(query=self._build_query(builder), adapter=builder.adapter)

    def paginate(self, builder: Builder, per_page: int, page: int) -> Page:
        """Execute the built query and return one page of matching instances."""
        result = self.search(builder)
        total = result.adapter.count_query(result.query)
        items = result.adapter.paginate_query(result.query, per_page=per_page, page=page)
        return Page(items, total=total, page=page, per_page=per_page)

    def map_ids(self, results: _DatabaseSearchResult) -> list[Any]:
        """Execute the query and return the scout keys of matching instances."""
        instances = results.adapter.execute_query(results.query)
        return [results.adapter.get_scout_key(instance) for instance in instances]

    def map(self, builder: Builder, results: _DatabaseSearchResult, model: type) -> list[Any]:
        """Execute the query and return matching model instances directly.

        Unlike a third-party engine, there's no separate "look up ids, then
        fetch models" step: the database engine's query already targets the
        model's own table.
        """
        return results.adapter.execute_query(results.query)

    def get_total_count(self, results: _DatabaseSearchResult) -> int:
        """Return the number of rows matching the built query."""
        return results.adapter.count_query(results.query)
