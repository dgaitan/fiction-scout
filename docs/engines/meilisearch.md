# `meilisearch` engine

Talks to a self-hosted or embedded Meilisearch server via the official
`meilisearch` Python client. Unlike Algolia, Meilisearch ships as a single
binary/Docker image, so you can run it locally.

```bash
pip install "fiction-scout[meilisearch]"
```

## Connecting

```python
FICTION_SCOUT = {
    "driver": "meilisearch",
    "meilisearch_url": "http://127.0.0.1:7700",  # or set MEILISEARCH_URL
    "meilisearch_api_key": "...",                  # or set MEILISEARCH_API_KEY
}
```

| Key | Env var fallback | Default if neither set | Meaning |
|---|---|---|---|
| `meilisearch_url` | `MEILISEARCH_URL` | `http://127.0.0.1:7700` | Base URL of your Meilisearch server. |
| `meilisearch_api_key` | `MEILISEARCH_API_KEY` | `""` (no key) | An admin/master key, needed for anything beyond public search on a server that requires auth. A fresh local server with no `--master-key` needs no key at all. |

Unlike Algolia, there's no eager credential check — a Meilisearch server
running with no auth configured is a completely valid zero-config setup, so
a blank `meilisearch_api_key` is not treated as an error.

You can also inject a pre-built client directly, bypassing this resolution
entirely (this is what the test suite's mocked tier does):

```python
from meilisearch import Client
from fiction_scout.engines.meilisearch import MeilisearchEngine

engine = MeilisearchEngine(client=Client("http://127.0.0.1:7700", "masterKey"))
```

## Behavior

- `update()` → `index.add_documents`, with the model's primary key passed
  explicitly (`adapter.get_scout_key_name(model)`) — unlike Algolia,
  Meilisearch preserves the scout key's original type (int, string,
  whatever the model uses) rather than coercing it to a string.
- `delete()` → `index.delete_documents(ids=...)` — the client itself emits
  a `DeprecationWarning` here (Meilisearch's newer API prefers
  `filter=`-based deletion), left as-is deliberately: filtering by the
  primary key would require that field to be a configured filterable
  attribute, which isn't guaranteed. `flush()` → `index.delete_all_documents()`
  — empties the index but does **not** delete it: searchable attributes and
  ranking rules configured on the index survive a flush.
- `search()`/`.get()`/`.paginate()` → one `index.search(term, params)` call
  per query, with `offset`/`limit` and (if any `.where()`s are set)
  `filter` all sent together in a single request — real model instances
  are then fetched back via `adapter.fetch_by_ids`.
- `create_index()` is a **real, idempotent get-or-create** — the one place
  this engine's shape diverges from Algolia's (which has no create-index
  call at all). It fetches the index by name first and only calls the
  create endpoint if missing, then waits for that creation task to finish
  before returning (idempotency is meaningless without the completion
  guarantee: two `create_index()` calls issued back-to-back without
  waiting could both see "not found" and the second would error).
  `update`/`delete`/`flush` do **not** wait for their tasks — only the
  method whose contract is idempotency needs the wait.
- Searching a model that has never been synced raises `index_not_found` at
  the Meilisearch API level rather than returning empty results — since
  Meilisearch only creates an index implicitly on first write. This engine
  catches that specific error and returns zero results instead of
  propagating it, so an unsynced model behaves like an empty index rather
  than an error.
- `.where()`/`.where_in()`/`.where_not_in()` translate into Meilisearch's
  `filter` syntax — see [Where clauses](#where-clauses) below. Filtering on
  a field that isn't declared filterable raises `UnfilterableAttributeError`
  rather than a raw `MeilisearchApiError` — see
  [Error handling](#error-handling).

## Index prefix / multi-tenancy

```python
FICTION_SCOUT = {"driver": "meilisearch", "index_prefix": f"{tenant_slug}_"}
```

Prepended to every index name this engine resolves (`update`, `delete`,
`flush`, `search`, `create_index`, `delete_index`, `sync-index-settings`).
See [Configuration: multi-tenancy](../configuration.md#multi-tenancy-with-index_prefix).

## Index settings

Each model gets its own Meilisearch index, and each index needs its own
settings — `filterable_attributes` for `Post` almost never matches what
`Author` needs. Settings are therefore nested under `extra["index_settings"]`,
keyed by the model's dotted path (the same path you pass to
`sync-index-settings`):

```python
FICTION_SCOUT = {
    "driver": "meilisearch",
    "meilisearch_url": "http://127.0.0.1:7700",
    "meilisearch_api_key": "...",
    "index_settings": {
        "myapp.models.Post": {
            "filterable_attributes": ["category", "status"],
            "sortable_attributes": ["views"],
        },
        "myapp.models.Author": {
            "filterable_attributes": ["country"],
        },
    },
}
```

```bash
fiction-scout create-index myapp.models.Post   # only needed before the first sync
fiction-scout sync-index-settings myapp.models.Post
# or, from Django:
python manage.py fiction_scout sync-index-settings myapp.models.Post
```

`sync-index-settings` only ever applies `index_settings["myapp.models.Post"]`
to the `Post` index — `Author`'s settings never leak into it, and vice
versa. See [Configuration: per-model index settings](../configuration.md#per-model-index-settings)
for the full rationale.

`update_index_settings` calls `index.update_settings` with just that
model's entry. Config keys use this project's snake_case convention and are
mapped to the camelCase keys Meilisearch's REST API expects (the full table
below); any key not in that table — including unrelated entries like
`meilisearch_url` or another model's settings — is silently dropped, not
sent. Waits for the settings task to finish before returning, same as
`create_index`.

**Settings that trigger a full reindex when changed**: `searchable_attributes`,
`filterable_attributes`, `sortable_attributes`, `stop_words`, `synonyms`,
`typo_tolerance`, `embedders`, `dictionary`, `proximity_precision`,
`separator_tokens`, `non_separator_tokens`. `ranking_rules`, `pagination`, `faceting`, and
`search_cutoff_ms` don't. This is a Meilisearch-server-side cost, not
something fiction-scout controls — worth knowing before running
`sync-index-settings` against a large existing index in production.

### Full settings reference

Every key below is accepted by `update_index_settings`/`sync-index-settings`
— this is the complete `_MEILISEARCH_SETTINGS_KEYS` whitelist, nothing
more, nothing less.

| Key (snake_case) | Wire name | Type | What it does |
|---|---|---|---|
| `searchable_attributes` | `searchableAttributes` | `list[str]` | Which fields are searched, in priority order — earlier entries in the array rank higher. Default: every field (`["*"]`). Changing this triggers a reindex. |
| `filterable_attributes` | `filterableAttributes` | `list[str]` (or granular objects, see below) | **Required for `.where()`/`.where_in()`/`.where_not_in()` to work at all.** Default: empty — filters don't work on anything until this is set. Changing this triggers a reindex. |
| `sortable_attributes` | `sortableAttributes` | `list[str]` | Attributes usable for `.orderBy()`-style sorting via the raw Meilisearch client (fiction-scout's own `Builder` doesn't expose a sort API yet — see [Known v1 limitations](#known-v1-limitations)). Default: empty. Changing this triggers a reindex. |
| `ranking_rules` | `rankingRules` | `list[str]` | The ranking formula. Default: `["words", "typo", "proximity", "attribute", "sort", "exactness"]`. Append custom rules like `"release_date:desc"` or `"rank:desc"` on a sortable/filterable attribute. |
| `distinct_attribute` | `distinctAttribute` | `str` | Deduplicates results to one hit per unique value of this attribute (e.g. one hit per `product_id` across color variants). |
| `stop_words` | `stopWords` | `list[str]` | Words ignored entirely during search (e.g. `["the", "a", "an"]`). Default: empty. Changing this triggers a reindex. |
| `synonyms` | `synonyms` | `dict[str, list[str]]` | Bidirectional-if-you-declare-both-ways synonym map, e.g. `{"wolverine": ["xmen", "logan"], "logan": ["wolverine"]}`. Default: empty. Changing this triggers a reindex. |
| `typo_tolerance` | `typoTolerance` | `dict` | Nested object — see below. Changing this triggers a reindex. |
| `pagination` | `pagination` | `dict` | Nested object, currently just `{"max_total_hits": <int>}` — caps how many total hits Meilisearch will rank per query (default `1000`). Set this to a realistic max page depth (e.g. `100`–`200`) to avoid wasted ranking work on deep pagination nobody uses. |
| `faceting` | `faceting` | `dict` | Nested object — see below. |
| `embedders` | `embedders` | `dict` | Vector/hybrid-search embedder configuration (e.g. `{"default": {"source": "userProvided"}}` for bring-your-own embeddings, or an OpenAI-backed embedder). Out of scope for fiction-scout's own filter/search API, but the raw dict passes through untouched if you're using Meilisearch's hybrid search directly. Changing this triggers a reindex. |
| `separator_tokens` | `separatorTokens` | `list[str]` | Extra characters/strings treated as word boundaries, beyond whitespace/punctuation — e.g. `["|"]` so `"a|b"` indexes as two words. Changing this triggers a reindex. |
| `non_separator_tokens` | `nonSeparatorTokens` | `list[str]` | Characters that should stay part of a word rather than acting as a boundary — e.g. `["+", "#"]` so `"C++"`/`"C#"` aren't split. Changing this triggers a reindex. |
| `dictionary` | `dictionary` | `list[str]` | Custom multi-character tokens Meilisearch should treat as a single unit rather than splitting — useful for domain terms, abbreviations with dots (`"J. R. R. Tolkien"`), or languages without whitespace word boundaries (Japanese). Default: empty. Changing this triggers a reindex. |
| `proximity_precision` | `proximityPrecision` | `str` | `"byWord"` (default, precise but more indexing work) or `"byAttribute"` (faster, coarser proximity ranking — treats a whole attribute as one unit for proximity purposes). Changing this triggers a reindex. |
| `search_cutoff_ms` | `searchCutoffMs` | `int` | Hard cap, in milliseconds, on how long Meilisearch spends ranking a single query before returning whatever it has. Useful for guaranteeing latency on huge indexes at the cost of possibly-incomplete ranking. |

#### `typo_tolerance` (nested)

```python
"typo_tolerance": {
    "enabled": True,
    "min_word_size_for_typos": {"one_typo": 5, "two_typos": 9},
    "disable_on_attributes": ["sku"],
    "disable_on_words": ["Nginx"],
},
```

Wire form: `enabled` (bool, default `true`), `minWordSizeForTypos.oneTypo`/
`twoTypos` (default `5`/`9`), `disableOnAttributes` (list), `disableOnWords`
(list). fiction-scout passes this dict straight through to Meilisearch's
`typoTolerance` key — write it with the same snake_case-outer/inner-keys
convention shown above; Meilisearch's client SDKs use camelCase for the
inner keys too (`minWordSizeForTypos`), so when constructing this dict
directly, match whatever your Meilisearch server version expects (check
`GET /indexes/{index}/settings/typo-tolerance` if unsure).

#### `faceting` (nested)

```python
"faceting": {
    "max_values_per_facet": 200,
    "sort_facet_values_by": {"brand": "count", "*": "alpha"},
},
```

`max_values_per_facet` (int, default `100`) caps facet-distribution size.
`sort_facet_values_by` maps an attribute name (or `"*"` as a wildcard
default) to `"count"` (most frequent first) or `"alpha"`.

#### `filterable_attributes` (granular form)

Newer Meilisearch versions accept either a flat list of attribute names, or
a list of pattern objects for per-attribute feature control:

```python
"filterable_attributes": [
    {
        "attribute_patterns": ["*"],
        "features": {
            "facet_search": False,
            "filter": {"equality": True, "comparison": False},
        },
    },
    {
        "attribute_patterns": ["price", "rating"],
        "features": {
            "facet_search": False,
            "filter": {"equality": True, "comparison": True},
        },
    },
],
```

`filter.equality` enables `=`, `!=`, `IN`, `NOT IN`, `IS NULL`,
`IS NOT NULL`, `IS EMPTY`, `IS NOT EMPTY`, `EXISTS`, `NOT EXISTS`.
`filter.comparison` enables `>`, `>=`, `<`, `<=`, `TO` (range). This lets
you, for example, allow numeric range filtering on `price`/`rating` while
keeping every other attribute equality-only — useful for controlling
indexing cost on high-cardinality attributes.

### Every setting at once

```python
FICTION_SCOUT = {
    "driver": "meilisearch",
    "meilisearch_url": "http://127.0.0.1:7700",
    "meilisearch_api_key": "...",
    "index_settings": {
        "myapp.models.Movie": {
            "searchable_attributes": ["title", "overview", "genres"],
            "filterable_attributes": ["genres", "release_date", "director"],
            "sortable_attributes": ["title", "release_date"],
            "ranking_rules": [
                "words", "typo", "proximity", "attribute",
                "sort", "exactness", "release_date:desc", "rank:desc",
            ],
            "distinct_attribute": "movie_id",
            "stop_words": ["the", "a", "an"],
            "synonyms": {"wolverine": ["xmen", "logan"], "logan": ["wolverine"]},
            "typo_tolerance": {
                "min_word_size_for_typos": {"one_typo": 8, "two_typos": 10},
                "disable_on_attributes": ["title"],
            },
            "pagination": {"max_total_hits": 5000},
            "faceting": {"max_values_per_facet": 200},
            "separator_tokens": ["|"],
            "non_separator_tokens": ["+", "#"],
            "proximity_precision": "byWord",
            "search_cutoff_ms": 150,
        },
    },
}
```

## Where clauses

`.where()`/`.where_in()`/`.where_not_in()` compile to Meilisearch's
`filter` string syntax, built by `MeilisearchEngine._filters()` — mirroring
Laravel Scout's `MeilisearchEngine::filters()` value-type handling exactly.

| Value type | Rendering |
|---|---|
| `bool` | `true`/`false` (bare, unquoted) |
| `None` | `IS NULL` clause, e.g. `.where("archived_at", None)` → `archived_at IS NULL` |
| `int`/`float` | bare, unquoted (`views = 42`) |
| anything else (`str`, ...) | double-quoted (`status = "published"`) |

| fiction-scout | Meilisearch `filter` |
|---|---|
| `.where("status", "published")` | `status = "published"` |
| `.where("views", 42)` | `views = 42` |
| `.where("archived", False)` | `archived = false` |
| `.where("deleted_at", None)` | `deleted_at IS NULL` |
| `.where_in("category", ["a", "b"])` | `category IN ["a", "b"]` |
| `.where_in("category", [])` | `category IN []` (valid, always false — no sentinel needed) |
| `.where_not_in("category", ["c"])` | `category NOT IN ["c"]` |
| `.where("a", 1).where_in("b", ["x"])` | `a = 1 AND b IN ["x"]` — every clause is `AND`-joined |

```python
# Single equality filter
Movie.search("wolverine").where("director", "James Mangold").get()

# Numeric filter
Movie.search().where("release_year", 2017).get()

# Boolean / null filters
Movie.search().where("is_franchise", True).get()
Movie.search().where("removed_at", None).get()

# Combined filters — all AND-joined
Movie.search("x-men").where("release_year", 2017).where_in("genre", ["action", "drama"]).get()

# .paginate() and .raw() accept the same where-clauses
Movie.search("x-men").where_not_in("genre", ["horror"]).paginate(per_page=10, page=1)
```

Every field referenced by a `.where()` must be declared in that index's
`filterable_attributes` (see above), or the request is rejected — see the
next section.

## Error handling

`MeilisearchEngine._run_search()` translates the SDK's `MeilisearchApiError`
into fiction-scout's own exceptions (subclasses of `FictionScoutError`,
importable from `fiction_scout.exceptions`) in two specific cases; every
other `MeilisearchApiError` (and connection failures) propagates as the raw
SDK exception today — unlike `AlgoliaEngine`, this engine doesn't yet wrap
credential/connection failures.

| Exception | Raised when | Example trigger |
|---|---|---|
| `UnfilterableAttributeError` | `MeilisearchApiError.code == "invalid_search_filter"` — a `.where()`/`.where_in()`/`.where_not_in()` field isn't in that index's `filterable_attributes`. | `Movie.search().where("release_year", 2000).get()` before running `sync-index-settings` for that field. |
| *(no exception — empty result)* | `MeilisearchApiError.code == "index_not_found"` — the model has never been synced, so its index doesn't exist yet. | `Movie.search("x").get()` on a model with zero indexed records. Treated as "empty index," not an error. |

```python
from fiction_scout.exceptions import UnfilterableAttributeError

try:
    Movie.search().where("release_year", 1999).get()
except UnfilterableAttributeError as exc:
    # "The 'meilisearch' driver rejected a filter: ... A field passed to
    #  .where()/.where_in()/.where_not_in() must be listed in this index's
    #  'filterable_attributes' setting. Add it under this model's entry in
    #  FICTION_SCOUT['extra']['index_settings'] ..."
    print(exc)
```

`IndexSettingsNotSupportedError` never actually happens for `meilisearch`
(it does support settings) — it's only relevant for drivers that don't
override `update_index_settings` at all.

## Known v1 limitations

- **Soft-deleted records are removed from the index entirely**, not tagged
  and kept — `with_trashed()`/`only_trashed()` only work against the
  `database`/`collection` engines. See
  [Indexing: soft delete](../indexing.md#soft-delete).
- **No sort API on `Builder` yet.** `sortable_attributes` can be configured
  and `ranking_rules` can reference a sortable attribute for a fixed sort
  order, but there's no `.orderBy()`-equivalent on fiction-scout's
  `Builder` for a caller-chosen per-query sort — only Meilisearch's own
  client, used directly, exposes that today.
- **No async variant** — same as every other engine in v1.

## Testing

Unlike Algolia, Meilisearch ships as a single binary with an official
Docker image, so it's genuinely testable without mocking. The project's
test suite runs two tiers:

- **Mocked-client tier** (`tests/test_meilisearch/test_meilisearch_engine.py`)
  — runs unconditionally, using a hand-rolled fake client
  (`tests/support.py`'s `FakeMeilisearchClient`/`FakeMeilisearchIndex`), not
  `unittest.mock`. Supports injectable faults
  (`search_raises_index_not_found`, `search_raises_invalid_filter`) built
  from the SDK's own real `MeilisearchApiError` class, so error-path tests
  exercise real exception-handling logic without a live server.
- **Live-server tier** (`tests/test_meilisearch/test_meilisearch_live.py`)
  — a session-scoped fixture launches the `meilisearch` binary on a random
  port if it's on `PATH`, or connects to `MEILISEARCH_TEST_URL` if set.
  Skipped (not failed) when neither is available, so `nox -s test_meilisearch`
  degrades gracefully on a machine without the binary/Docker.

```python
from fiction_scout.engines.meilisearch import MeilisearchEngine
from tests.support import FakeMeilisearchClient

# Happy path
client = FakeMeilisearchClient(search_hits=[{"id": 1, "title": "..."}], estimated_total_hits=1)
engine = MeilisearchEngine(client=client)

# Simulated "field not filterable" failure
client = FakeMeilisearchClient(search_raises_invalid_filter=True)
engine = MeilisearchEngine(client=client)
```

See `src/fiction_scout/engines/meilisearch.py`'s module docstring for the
full test-strategy rationale.
