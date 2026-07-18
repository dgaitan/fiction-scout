"""Algolia search engine: talks to Algolia's SaaS index API.

**Test strategy (recorded before writing tests against this module, per the
same bar Sprint 6's Celery-dispatcher docstring set):** Algolia has no
self-hosted/embeddable mode, so "real" tests either hit a live account or
mock the HTTP boundary. `tests/test_algolia/` runs a mocked-client unit tier
unconditionally (via a small hand-rolled fake client, matching this
project's existing `SpyEngine`/`FakeAdapter` test-double style rather than
`unittest.mock`) — it asserts fiction-scout calls `save_objects`/
`delete_objects`/`clear_objects`/`search_single_index` with the right
arguments, which is what actually proves this engine's own logic is
correct, independent of network access. A live-integration tier against a
real Algolia account is deliberately not built: Sprint 7's own Gherkin
specs don't call for one, and `AlgoliaEngine(client=...)`'s injectable
client already makes the mocked tier a genuine substitute for exercising
this module's logic.

**`create_index` is unsupported, not a settings call:** unlike Meilisearch
(Sprint 8), Algolia has no explicit index-creation API — an index is
created automatically the first time a record is written to it.
`create_index` therefore raises `IndexCreationNotSupportedError` instead of
either silently no-op'ing (which would let a caller believe an empty index
now exists, when in fact nothing does until the first write) or attempting
an API call that doesn't exist. Mirrors Laravel Scout's own
`AlgoliaEngine::createIndex()`, which throws `NotSupportedException`.

**Soft-deleted records are excluded from the index entirely, not tagged:**
unlike Laravel Scout (which keeps them in-index behind a `__soft_deleted`
filterable attribute so `withTrashed()` still works), fiction-scout v1
keeps its existing simpler behavior — `with_trashed()`/`only_trashed()`
stay database-engine-only, confirmed with the user 2026-07-18. No
`__soft_deleted` metadata is written; a soft-deleted instance is removed
from this index entirely via the existing `make_unsearchable` path.

**Known, documented limitation — `where`/`where_in`/`where_not_in` are not
translated to Algolia filters in v1:** Sprint 7's Gherkin specs cover term
search, create/delete/flush, and the empty-searchable-array exclusion —
none of them exercise `Builder.where*`. Wiring those into Algolia's
`filters`/`facetFilters` syntax is real, non-trivial work out of this
sprint's scope; a caller using `.where()` against the `algolia` driver
today gets unfiltered results back, not an error. Revisit before shipping
`.where()` support for this driver.

**Scout key / Algolia `objectID` type mismatch:** Algolia requires
`objectID` to be a string. A model's own scout key may not be (an integer
primary key, for example), so `update()` always writes
`str(adapter.get_scout_key(instance))`, and `map()`/`map_ids()` compare
ids as strings via `engines._external_index.fetch_matched_models` — see
that module for why.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from fiction_scout.dependencies import require_installed
from fiction_scout.engines._external_index import fetch_matched_models
from fiction_scout.engines.base import Engine, Page
from fiction_scout.exceptions import IndexCreationNotSupportedError

if TYPE_CHECKING:
    from algoliasearch.search.client import SearchClientSync

    from fiction_scout.protocols import SearchableAdapter
    from fiction_scout.search.builder import Builder

# Algolia's own hard cap on hits returned by a single `search_single_index`
# call — used as the page size for unbounded `.get()`/`.raw()` calls, not a
# fiction-scout-chosen default.
_MAX_HITS_PER_PAGE = 1000


@dataclass
class _AlgoliaSearchResult:
    """This engine's raw result type: the matched hits plus the total count."""

    hits: list[Any] = field(default_factory=list)
    total: int = 0


class AlgoliaEngine(Engine):
    """Indexes and searches models via Algolia's SaaS API."""

    def __init__(
        self,
        app_id: str = "",
        api_key: str = "",
        *,
        client: SearchClientSync | None = None,
    ) -> None:
        require_installed(
            feature="algolia", module_name="algoliasearch", extra="algolia"
        )
        if client is None:
            from algoliasearch.search.client import SearchClientSync

            client = SearchClientSync(app_id, api_key)
        self._client = client

    def update(self, models: list[Any], adapter: SearchableAdapter) -> None:
        if not models:
            return
        index_name = adapter.searchable_as(type(models[0]))
        records = [
            {**array, "objectID": str(adapter.get_scout_key(instance))}
            for instance in models
            if (array := adapter.to_searchable_array(instance))
        ]
        if not records:
            return
        self._client.save_objects(index_name=index_name, objects=records)

    def delete(self, models: list[Any], adapter: SearchableAdapter) -> None:
        if not models:
            return
        index_name = adapter.searchable_as(type(models[0]))
        object_ids = [str(adapter.get_scout_key(instance)) for instance in models]
        self._client.delete_objects(index_name=index_name, object_ids=object_ids)

    def flush(self, model: type, adapter: SearchableAdapter) -> None:
        self._client.clear_objects(index_name=adapter.searchable_as(model))

    def create_index(self, name: str, **options: Any) -> None:
        raise IndexCreationNotSupportedError(
            "algolia",
            "Algolia indexes are created automatically the first time a "
            "record is written to them.",
        )

    def delete_index(self, name: str) -> None:
        self._client.delete_index(index_name=name)

    def _index_name(self, builder: Builder) -> str:
        return builder.index or builder.adapter.searchable_as(builder.model)

    def _run_search(
        self, builder: Builder, *, page: int, hits_per_page: int
    ) -> _AlgoliaSearchResult:
        response = self._client.search_single_index(
            index_name=self._index_name(builder),
            search_params={
                "query": builder.term,
                "page": page,
                "hitsPerPage": hits_per_page,
            },
        )
        return _AlgoliaSearchResult(
            hits=list(response.hits), total=response.nb_hits or 0
        )

    def search(self, builder: Builder) -> _AlgoliaSearchResult:
        """Fetch up to Algolia's max hits per page (1000) in a single page."""
        return self._run_search(builder, page=0, hits_per_page=_MAX_HITS_PER_PAGE)

    def paginate(self, builder: Builder, per_page: int, page: int) -> Page:
        result = self._run_search(builder, page=page - 1, hits_per_page=per_page)
        return Page(
            self.map(builder, result, builder.model),
            total=result.total,
            page=page,
            per_page=per_page,
        )

    def map_ids(self, results: _AlgoliaSearchResult) -> list[Any]:
        return [hit.object_id for hit in results.hits]

    def map(
        self, builder: Builder, results: _AlgoliaSearchResult, model: type
    ) -> list[Any]:
        ids = self.map_ids(results)
        return fetch_matched_models(builder.adapter, model, ids)

    def get_total_count(self, results: _AlgoliaSearchResult) -> int:
        return results.total
