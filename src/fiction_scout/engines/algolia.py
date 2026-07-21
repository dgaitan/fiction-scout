"""Algolia search engine: talks to Algolia's SaaS index API.

**Test strategy (recorded before writing tests against this module, per the
same bar the Celery dispatcher's own design-decision docstring set):**
Algolia has no self-hosted/embeddable mode, so "real" tests either hit a
live account or mock the HTTP boundary. `tests/test_algolia/` runs a
mocked-client unit tier unconditionally (via a small hand-rolled fake
client, matching this project's existing `SpyEngine`/`FakeAdapter`
test-double style rather than `unittest.mock`) — it asserts fiction-scout
calls `save_objects`/`delete_objects`/`clear_objects`/`search_single_index`
with the right arguments, which is what actually proves this engine's own
logic is correct, independent of network access. A live-integration tier
against a real Algolia account is deliberately not built: nothing in this
module's own Gherkin specs calls for one, and `AlgoliaEngine(client=...)`'s
injectable client already makes the mocked tier a genuine substitute for
exercising this module's logic.

**`create_index` is unsupported, not a settings call:** unlike Meilisearch,
Algolia has no explicit index-creation API — an index is
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

**`where`/`where_in`/`where_not_in` translate to Algolia's `filters` syntax:**
`_filters()` mirrors Laravel Scout's `AlgoliaEngine::filters()` — see that
method's docstring for the exact translation rules and the sentinel/
combinator choices it reproduces.

**`update_index_settings` has a real API, unlike `create_index`:** Algolia's
lack of an index-creation endpoint doesn't extend to settings — `set_settings`
is a real call. The whitelist of accepted keys is read straight off the
installed `algoliasearch` SDK's own `IndexSettings` model fields rather than
hand-maintained, so it can't silently drift from whatever version of the SDK
is actually installed; see `update_index_settings`'s own inline comment and
`MeilisearchEngine.update_index_settings`'s docstring paragraph for why
unrelated `config.extra` keys (like `meilisearch_url`) need to be dropped
rather than sent, here too.

**Scout key / Algolia `objectID` type mismatch:** Algolia requires
`objectID` to be a string. A model's own scout key may not be (an integer
primary key, for example), so `update()` always writes
`str(adapter.get_scout_key(instance))`, and `map()`/`map_ids()` compare
ids as strings via `engines._external_index.fetch_matched_models` — see
that module for why.

**Connection/auth errors are translated, not left as raw SDK tracebacks:**
a bad `algolia_app_id` doesn't produce an auth error — Algolia derives its
request hostname from the app id, so a wrong one fails DNS resolution
before any HTTP response exists, and `algoliasearch`'s own
`TransporterSync.request` only catches `requests.Timeout`, not
`requests.ConnectionError`, so that failure would otherwise reach the
caller as a raw `urllib3`/`requests` traceback. `_translate_client_errors`
catches that, plus the SDK's own `AlgoliaUnreachableHostException` and
401/403 `RequestException`, and re-raises as `EngineConnectionError`/
`EngineAuthenticationError` with a hint pointing at credentials.
`__init__` also checks for blank `app_id`/`api_key` before ever
constructing a client, so missing credentials fail immediately with
`MissingCredentialsError` instead of on the first network call. A search
whose `filters` reference a field that isn't declared in the index's
`attributesForFaceting` gets the same treatment — Algolia rejects it with a
400 `RequestException` naming that setting, which `_translate_client_errors`
recognizes and re-raises as `UnfilterableAttributeError` with a hint
pointing at `attributes_for_faceting`/`sync-index-settings`.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from fiction_scout.dependencies import require_installed
from fiction_scout.engines._external_index import fetch_matched_models
from fiction_scout.engines.base import Engine, Page
from fiction_scout.exceptions import (
    EngineAuthenticationError,
    EngineConnectionError,
    IndexCreationNotSupportedError,
    MissingCredentialsError,
    UnfilterableAttributeError,
)

if TYPE_CHECKING:
    from algoliasearch.search.client import SearchClientSync

    from fiction_scout.protocols import SearchableAdapter
    from fiction_scout.search.builder import Builder

# Algolia's own hard cap on hits returned by a single `search_single_index`
# call — used as the page size for unbounded `.get()`/`.raw()` calls, not a
# fiction-scout-chosen default.
_MAX_HITS_PER_PAGE = 1000

_CREDENTIALS_HINT = (
    "Set 'algolia_app_id'/'algolia_api_key' in FICTION_SCOUT['extra'], or "
    "the ALGOLIA_APP_ID/ALGOLIA_API_KEY environment variables."
)
_AUTH_HINT = (
    "Verify 'algolia_app_id'/'algolia_api_key' (or ALGOLIA_APP_ID/"
    "ALGOLIA_API_KEY) are correct and that the key has the permissions "
    "this operation needs."
)
_CONNECTION_HINT = (
    "This is commonly caused by an incorrect 'algolia_app_id' — Algolia "
    "derives its request hostname from the app id, so a wrong one fails to "
    "resolve rather than returning an auth error. Verify "
    "'algolia_app_id'/ALGOLIA_APP_ID, then check network connectivity."
)
_FACETING_HINT = (
    "A field passed to .where()/.where_in()/.where_not_in() must be listed "
    "in this index's 'attributes_for_faceting' setting. Add it under this "
    "model's entry in FICTION_SCOUT['extra']['index_settings'] (keyed by "
    "the model's dotted path) and run 'sync-index-settings <model>' (or "
    "'manage.py fiction_scout sync-index-settings <model>'), then retry."
)


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
        index_prefix: str = "",
    ) -> None:
        require_installed(
            feature="algolia", module_name="algoliasearch", extra="algolia"
        )
        if client is None:
            missing = [
                key
                for key, value in (
                    ("algolia_app_id", app_id),
                    ("algolia_api_key", api_key),
                )
                if not value
            ]
            if missing:
                raise MissingCredentialsError("algolia", missing, _CREDENTIALS_HINT)
            from algoliasearch.search.client import SearchClientSync

            client = SearchClientSync(app_id, api_key)
        self._client = client
        self._index_prefix = index_prefix

    @contextmanager
    def _translate_client_errors(self) -> Iterator[None]:
        from algoliasearch.http.exceptions import (
            AlgoliaUnreachableHostException,
            RequestException,
        )
        from requests.exceptions import ConnectionError as RequestsConnectionError

        try:
            yield
        except RequestException as exc:
            if exc.status_code in (401, 403):
                raise EngineAuthenticationError(
                    "algolia", str(exc), _AUTH_HINT
                ) from exc
            if exc.status_code == 400 and "attributesForFaceting" in str(exc):
                raise UnfilterableAttributeError(
                    "algolia", str(exc), _FACETING_HINT
                ) from exc
            raise
        except (AlgoliaUnreachableHostException, RequestsConnectionError) as exc:
            raise EngineConnectionError("algolia", str(exc), _CONNECTION_HINT) from exc

    def index_name_for(self, model: type, adapter: SearchableAdapter) -> str:
        return f"{self._index_prefix}{adapter.searchable_as(model)}"

    def update(self, models: list[Any], adapter: SearchableAdapter) -> None:
        if not models:
            return
        index_name = self.index_name_for(type(models[0]), adapter)
        records = [
            {**array, "objectID": str(adapter.get_scout_key(instance))}
            for instance in models
            if (array := adapter.to_searchable_array(instance))
        ]
        if not records:
            return
        with self._translate_client_errors():
            self._client.save_objects(index_name=index_name, objects=records)

    def delete(self, models: list[Any], adapter: SearchableAdapter) -> None:
        if not models:
            return
        index_name = self.index_name_for(type(models[0]), adapter)
        object_ids = [str(adapter.get_scout_key(instance)) for instance in models]
        with self._translate_client_errors():
            self._client.delete_objects(index_name=index_name, object_ids=object_ids)

    def flush(self, model: type, adapter: SearchableAdapter) -> None:
        with self._translate_client_errors():
            self._client.clear_objects(index_name=self.index_name_for(model, adapter))

    def create_index(self, name: str, **options: Any) -> None:
        raise IndexCreationNotSupportedError(
            "algolia",
            "Algolia indexes are created automatically the first time a "
            "record is written to them.",
        )

    def delete_index(self, name: str) -> None:
        with self._translate_client_errors():
            self._client.delete_index(index_name=name)

    def update_index_settings(
        self, model: type, adapter: SearchableAdapter, **settings: Any
    ) -> None:
        from algoliasearch.search.models.index_settings import IndexSettings

        # `IndexSettings.model_fields` is the SDK's own source of truth for
        # what a settings payload accepts, so this whitelist can't drift out
        # of sync with the installed `algoliasearch` version the way a
        # hand-maintained key list could. Everything else — including
        # unrelated `config.extra` keys like `algolia_app_id` that the CLI's
        # `sync-index-settings` command splats in alongside real settings —
        # is dropped, not sent. See `MeilisearchEngine.update_index_settings`
        # for the same pattern applied to a client without a typed model.
        known_fields = set(IndexSettings.model_fields.keys())
        payload = {key: value for key, value in settings.items() if key in known_fields}
        if not payload:
            return
        index_name = self.index_name_for(model, adapter)
        # `set_settings` accepts a plain dict, but only an actual
        # `IndexSettings` instance gets alias-translated (snake_case field
        # name -> Algolia's camelCase wire name, e.g.
        # attributes_for_faceting -> attributesForFaceting) by the SDK's
        # serializer — a raw dict is sent to Algolia's REST API verbatim,
        # which then rejects the unrecognized snake_case key. Round-tripping
        # through `IndexSettings(**payload).to_dict()` gets the correct
        # wire-format keys while keeping `index_settings` a plain dict, same
        # shape the test double (`FakeAlgoliaClient`) expects.
        wire_payload = IndexSettings(**payload).to_dict()
        with self._translate_client_errors():
            self._client.set_settings(
                index_name=index_name, index_settings=wire_payload
            )

    def _index_name(self, builder: Builder) -> str:
        return builder.index or self.index_name_for(builder.model, builder.adapter)

    def _filters(self, builder: Builder) -> str:
        """Translate `Builder.where*` into Algolia's `filters` syntax.

        Mirrors Laravel Scout's `AlgoliaEngine::filters()` exactly (same
        `'0:1'` always-false sentinel for an empty `where_in`, same `(NOT
        field:'v1' OR NOT field:'v2')` combinator for `where_not_in`) — our
        `Builder.where()` only ever expresses equality, unlike Laravel's
        3-arg form, so the operator-branching half of their method doesn't
        apply here.
        """
        clauses = [f"{column}:'{value}'" for column, value in builder.wheres.items()]
        for column, values in builder.where_ins.items():
            if not values:
                clauses.append("0:1")
                continue
            clauses.append(
                "(" + " OR ".join(f"{column}:'{value}'" for value in values) + ")"
            )
        for column, values in builder.where_not_ins.items():
            if not values:
                continue
            clauses.append(
                "(" + " OR ".join(f"NOT {column}:'{value}'" for value in values) + ")"
            )
        return " AND ".join(clauses)

    def _run_search(
        self, builder: Builder, *, page: int, hits_per_page: int
    ) -> _AlgoliaSearchResult:
        search_params: dict[str, Any] = {
            "query": builder.term,
            "page": page,
            "hitsPerPage": hits_per_page,
        }
        filters = self._filters(builder)
        if filters:
            search_params["filters"] = filters
        with self._translate_client_errors():
            response = self._client.search_single_index(
                index_name=self._index_name(builder), search_params=search_params
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
