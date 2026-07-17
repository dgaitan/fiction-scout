"""The fluent search query builder returned by a searchable model's `.search()`."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable

if TYPE_CHECKING:
    from fiction_scout.engines.base import Engine, Page
    from fiction_scout.protocols import SearchableAdapter


class Builder:
    """Accumulates search constraints; engines read this state to execute.

    Constructed by a searchable model's `.search()` classmethod — not
    typically instantiated directly.
    """

    def __init__(
        self,
        model: type,
        query: str,
        *,
        engine: Engine,
        adapter: SearchableAdapter,
        callback: Callable[..., Any] | None = None,
    ) -> None:
        self.model = model
        self.query = query
        self.engine = engine
        self.adapter = adapter
        self.callback = callback
        self.wheres: dict[str, Any] = {}
        self.where_ins: dict[str, list[Any]] = {}
        self.where_not_ins: dict[str, list[Any]] = {}
        self.index: str | None = None
        self.query_callback: Callable[[Any], Any] | None = None
        self.with_trashed_ = False
        self.only_trashed_ = False

    def where(self, field: str, value: Any) -> Builder:
        """Constrain results to records where `field` equals `value`."""
        self.wheres[field] = value
        return self

    def where_in(self, field: str, values: list[Any]) -> Builder:
        """Constrain results to records where `field` is one of `values`."""
        self.where_ins[field] = values
        return self

    def where_not_in(self, field: str, values: list[Any]) -> Builder:
        """Constrain results to records where `field` is not one of `values`."""
        self.where_not_ins[field] = values
        return self

    def within(self, index: str) -> Builder:
        """Search a specific index instead of the model's default index."""
        self.index = index
        return self

    def query(self, callback: Callable[[Any], Any]) -> Builder:
        """Customize the query used to fetch matched model instances.

        For the database engine this callback's constraints apply directly
        to the underlying query, so it can also be used for filtering. For
        every other engine it only runs after matching records have already
        been fetched by scout key — it cannot filter there. This mirrors
        Scout's documented database-engine-only filtering caveat.
        """
        self.query_callback = callback
        return self

    def with_trashed(self) -> Builder:
        """Include soft-deleted records in the results."""
        self.with_trashed_ = True
        self.only_trashed_ = False
        return self

    def only_trashed(self) -> Builder:
        """Return only soft-deleted records."""
        self.only_trashed_ = True
        self.with_trashed_ = False
        return self

    def raw(self) -> Any:
        """Return the engine's raw, unmapped results."""
        return self.engine.search(self)

    def get(self) -> list[Any]:
        """Execute the search and return matching model instances."""
        return self.engine.get(self)

    def paginate(self, per_page: int = 15, page: int = 1) -> Page:
        """Execute the search and return one page of matching model instances."""
        return self.engine.paginate(self, per_page, page)
