"""Meilisearch search engine: talks to a self-hosted/embeddable Meilisearch server.

**Test strategy:** unlike Algolia, Meilisearch ships as a single binary and
an official Docker image, so it's genuinely testable without mocking.
`tests/test_meilisearch/test_meilisearch_engine.py` runs a mocked-client
unit tier unconditionally (same hand-rolled test-double style as
`FakeAlgoliaClient`), proving this engine's own logic in isolation.
`tests/test_meilisearch/test_meilisearch_live.py` runs the same contract
against a real server — a session-scoped fixture launches the `meilisearch`
binary on a random port if it's on `PATH`, or connects to
`MEILISEARCH_TEST_URL` if set — and is skipped (not failed) when neither is
available, so `nox -s test_meilisearch` degrades gracefully on a machine
without the binary/Docker.

**`create_index` is a real, idempotent get-or-create — the one place this
engine diverges from "same shape as Algolia":** Meilisearch has an explicit
index-creation API, so `create_index` fetches the index by name first and
only calls the create endpoint if it's missing, mirroring Laravel Scout's
`MeilisearchEngine::createIndex()`. Because "idempotent" is the entire point
of this method, it waits for the create task to finish before returning —
without that, two `create_index()` calls issued back-to-back could both see
"not found" and both attempt to create, turning the second into an error
instead of a no-op. `update`/`delete`/`flush` do **not** wait for their
tasks (same fire-and-forget shape as `AlgoliaEngine`) — only the method
whose contract is idempotency needs the completion guarantee.

**Soft-deleted records are excluded from the index entirely, not tagged:**
same v1 decision as `AlgoliaEngine` — no `__soft_deleted` filterable
attribute, `with_trashed()`/`only_trashed()` stay database-engine-only.

**`where`/`where_in`/`where_not_in` translate to Meilisearch's `filter`
syntax:** `_filters()` mirrors Laravel Scout's `MeilisearchEngine::filters()`
— see that method's docstring for the exact value-formatting and combinator
rules it reproduces. Unlike Laravel's own implementation, `.where()` against
a field that isn't a configured filterable attribute doesn't reach the
caller as a raw `MeilisearchApiError` — `_run_search` recognizes the SDK's
own `code == "invalid_search_filter"` and re-raises as
`UnfilterableAttributeError` with a hint pointing at `filterable_attributes`
and the `sync-index-settings` command (see "Index settings" below for how
to configure it).

**`delete_documents(ids=...)` triggers a `DeprecationWarning` from the
client itself** (in favor of `filter=`), left as-is because filtering by the
primary key requires that field to be a configured filterable attribute —
verified against a real server (`filter="id = 1"` fails with a task-level
error on a fresh index).

**`update_index_settings` whitelists known Meilisearch settings keys and
silently ignores the rest:** the CLI's `sync-index-settings` command
(`cli/commands/sync_index_settings.py`) splats fiction-scout's *entire*
`config.extra` dict as kwargs into this method — including connection
settings like `meilisearch_url`/`meilisearch_api_key` that have nothing to
do with index settings. `_MEILISEARCH_SETTINGS_KEYS` maps the snake_case
keys this project's config convention uses (`filterable_attributes`, etc.)
to the camelCase keys Meilisearch's REST API expects, and anything not in
that map — including those connection keys — is dropped rather than sent,
mirroring Laravel's `MeilisearchEngine::updateIndexSettings()`, which only
ever receives its own `index-settings` config sub-array in the first place.
Waits for the settings task to finish, same rationale as `create_index`.

**No `objectID`-style key normalization needed:** unlike Algolia (which
requires a string `objectID`), Meilisearch's primary key can be any string
or integer field already present on the document, and it echoes the value
back at its original type in search hits — `update()` just passes
`adapter.get_scout_key_name(model)` as the `primary_key` argument. `map()`
still routes through the shared `fetch_matched_models` helper (which
compares via `str()`) for consistency with every other external-index
engine, not because a mismatch exists here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from fiction_scout.dependencies import require_installed
from fiction_scout.engines._external_index import fetch_matched_models
from fiction_scout.engines.base import Engine, Page
from fiction_scout.exceptions import UnfilterableAttributeError

if TYPE_CHECKING:
    from meilisearch import Client

    from fiction_scout.protocols import SearchableAdapter
    from fiction_scout.search.builder import Builder

# Meilisearch's own default `pagination.maxTotalHits` setting — used as the
# page size for unbounded `.get()`/`.raw()` calls, not a fiction-scout-chosen
# default.
_MAX_HITS = 1000

_FACETING_HINT = (
    "A field passed to .where()/.where_in()/.where_not_in() must be listed "
    "in this index's 'filterable_attributes' setting. Add it under this "
    "model's entry in FICTION_SCOUT['extra']['index_settings'] (keyed by "
    "the model's dotted path) and run 'sync-index-settings <model>' (or "
    "'manage.py fiction_scout sync-index-settings <model>'), then retry."
)

# snake_case (this project's config convention) -> camelCase (Meilisearch's
# REST API) for every top-level key `index.update_settings()` accepts. Keys
# passed to `update_index_settings` that aren't in this map are dropped, not
# sent — see the module docstring's "Index settings" note.
_MEILISEARCH_SETTINGS_KEYS: dict[str, str] = {
    "searchable_attributes": "searchableAttributes",
    "filterable_attributes": "filterableAttributes",
    "sortable_attributes": "sortableAttributes",
    "ranking_rules": "rankingRules",
    "distinct_attribute": "distinctAttribute",
    "stop_words": "stopWords",
    "synonyms": "synonyms",
    "typo_tolerance": "typoTolerance",
    "pagination": "pagination",
    "faceting": "faceting",
    "embedders": "embedders",
    "separator_tokens": "separatorTokens",
    "non_separator_tokens": "nonSeparatorTokens",
    "dictionary": "dictionary",
    "proximity_precision": "proximityPrecision",
    "search_cutoff_ms": "searchCutoffMs",
}


@dataclass
class _MeilisearchSearchResult:
    """This engine's raw result type: matched hits, total, and the primary key field.

    Meilisearch hits are plain document dicts keyed by whatever field the
    model's own primary key uses (unlike Algolia's fixed `objectID`), so the
    field name has to travel with the result for `map_ids` to know which key
    to read off each hit.
    """

    hits: list[dict[str, Any]] = field(default_factory=list)
    total: int = 0
    primary_key_field: str = "id"


class MeilisearchEngine(Engine):
    """Indexes and searches models via a Meilisearch server."""

    def __init__(
        self,
        url: str = "http://127.0.0.1:7700",
        api_key: str = "",
        *,
        client: Client | None = None,
        index_prefix: str = "",
    ) -> None:
        require_installed(
            feature="meilisearch", module_name="meilisearch", extra="meilisearch"
        )
        if client is None:
            from meilisearch import Client as MeilisearchClient

            client = MeilisearchClient(url, api_key or None)
        self._client = client
        self._index_prefix = index_prefix

    def index_name_for(self, model: type, adapter: SearchableAdapter) -> str:
        return f"{self._index_prefix}{adapter.searchable_as(model)}"

    def update(self, models: list[Any], adapter: SearchableAdapter) -> None:
        if not models:
            return
        model = type(models[0])
        documents = [
            array
            for instance in models
            if (array := adapter.to_searchable_array(instance))
        ]
        if not documents:
            return
        index_name = self.index_name_for(model, adapter)
        primary_key = adapter.get_scout_key_name(model)
        self._client.index(index_name).add_documents(documents, primary_key=primary_key)

    def delete(self, models: list[Any], adapter: SearchableAdapter) -> None:
        if not models:
            return
        index_name = self.index_name_for(type(models[0]), adapter)
        ids = [adapter.get_scout_key(instance) for instance in models]
        self._client.index(index_name).delete_documents(ids)

    def flush(self, model: type, adapter: SearchableAdapter) -> None:
        self._client.index(self.index_name_for(model, adapter)).delete_all_documents()

    def create_index(self, name: str, **options: Any) -> None:
        from meilisearch.errors import MeilisearchApiError

        try:
            self._client.get_index(name)
            return
        except MeilisearchApiError as error:
            if error.code != "index_not_found":
                raise

        primary_key = options.get("primary_key")
        create_options = {"primaryKey": primary_key} if primary_key else None
        task = self._client.create_index(name, create_options)
        self._client.wait_for_task(task.task_uid)

    def delete_index(self, name: str) -> None:
        self._client.delete_index(name)

    def update_index_settings(
        self, model: type, adapter: SearchableAdapter, **settings: Any
    ) -> None:
        payload = {
            _MEILISEARCH_SETTINGS_KEYS[key]: value
            for key, value in settings.items()
            if key in _MEILISEARCH_SETTINGS_KEYS
        }
        if not payload:
            return
        index_name = self.index_name_for(model, adapter)
        task = self._client.index(index_name).update_settings(payload)
        self._client.wait_for_task(task.task_uid)

    def _index_name(self, builder: Builder) -> str:
        return builder.index or self.index_name_for(builder.model, builder.adapter)

    def _filters(self, builder: Builder) -> str:
        """Translate `Builder.where*` into Meilisearch's `filter` syntax.

        Mirrors Laravel Scout's `MeilisearchEngine::filters()` value-type
        handling (bool -> `true`/`false`, `None` -> `IS NULL`, numeric ->
        bare, else double-quoted string) and its `field IN [...]`/`field NOT
        IN [...]` combinators for `where_in`/`where_not_in`. Our `Builder`
        never carries Laravel's `BackedEnum` values, so that branch doesn't
        port over. An empty `where_in`/`where_not_in` list contributes no
        clause (unlike Algolia's `'0:1'` sentinel) since Meilisearch's `IN
        []`/`NOT IN []` are valid, unambiguous filter expressions on their
        own — no sentinel is needed to force a false/true match.
        """

        def format_value(value: Any) -> str:
            if isinstance(value, bool):
                return "true" if value else "false"
            if isinstance(value, (int, float)):
                return str(value)
            return f'"{value}"'

        clauses = []
        for column, value in builder.wheres.items():
            if value is None:
                clauses.append(f"{column} IS NULL")
            else:
                clauses.append(f"{column} = {format_value(value)}")
        for column, values in builder.where_ins.items():
            joined = ", ".join(format_value(value) for value in values)
            clauses.append(f"{column} IN [{joined}]")
        for column, values in builder.where_not_ins.items():
            joined = ", ".join(format_value(value) for value in values)
            clauses.append(f"{column} NOT IN [{joined}]")
        return " AND ".join(clauses)

    def _run_search(
        self, builder: Builder, *, offset: int, limit: int
    ) -> _MeilisearchSearchResult:
        from meilisearch.errors import MeilisearchApiError

        primary_key_field = builder.adapter.get_scout_key_name(builder.model)
        params: dict[str, Any] = {"offset": offset, "limit": limit}
        filters = self._filters(builder)
        if filters:
            params["filter"] = filters
        try:
            response = self._client.index(self._index_name(builder)).search(
                builder.term, params
            )
        except MeilisearchApiError as error:
            if error.code == "invalid_search_filter":
                raise UnfilterableAttributeError(
                    "meilisearch", str(error), _FACETING_HINT
                ) from error
            # A model with nothing indexed yet (no sync has run) has no
            # Meilisearch index at all, since Meilisearch only creates one
            # implicitly on first write — searching it is a normal "no
            # results yet" state, not an error, so it's treated the same as
            # an existing-but-empty index rather than propagating the 404.
            if error.code != "index_not_found":
                raise
            return _MeilisearchSearchResult(primary_key_field=primary_key_field)
        hits = list(response.get("hits", []))
        total = response.get("estimatedTotalHits", len(hits))
        return _MeilisearchSearchResult(
            hits=hits, total=total, primary_key_field=primary_key_field
        )

    def search(self, builder: Builder) -> _MeilisearchSearchResult:
        """Fetch up to Meilisearch's default max total hits (1000) in one page."""
        return self._run_search(builder, offset=0, limit=_MAX_HITS)

    def paginate(self, builder: Builder, per_page: int, page: int) -> Page:
        result = self._run_search(builder, offset=(page - 1) * per_page, limit=per_page)
        return Page(
            self.map(builder, result, builder.model),
            total=result.total,
            page=page,
            per_page=per_page,
        )

    def map_ids(self, results: _MeilisearchSearchResult) -> list[Any]:
        return [hit[results.primary_key_field] for hit in results.hits]

    def map(
        self, builder: Builder, results: _MeilisearchSearchResult, model: type
    ) -> list[Any]:
        ids = self.map_ids(results)
        return fetch_matched_models(builder.adapter, model, ids)

    def get_total_count(self, results: _MeilisearchSearchResult) -> int:
        return results.total
