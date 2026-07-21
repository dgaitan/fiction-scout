# `algolia` engine

Talks to Algolia's SaaS index API via the official `algoliasearch` Python
client (`SearchClientSync`). Algolia has no self-hosted mode — this engine
always talks to Algolia's cloud over HTTPS.

```bash
pip install "fiction-scout[algolia]"
```

## Connecting

```python
FICTION_SCOUT = {
    "driver": "algolia",
    "algolia_app_id": "...",   # or set the ALGOLIA_APP_ID env var
    "algolia_api_key": "...",  # or set the ALGOLIA_API_KEY env var
}
```

| Key | Env var fallback | Meaning |
|---|---|---|
| `algolia_app_id` | `ALGOLIA_APP_ID` | Your Algolia Application ID. Algolia derives the request hostname from this, so a wrong value fails DNS resolution rather than returning an auth error. |
| `algolia_api_key` | `ALGOLIA_API_KEY` | An **Admin API key** (or a key with `addObject`/`deleteObject`/`editSettings`/`deleteIndex` ACLs, depending on which operations you use) — not the public search-only key. |

Both keys are read from `FICTION_SCOUT["algolia_app_id"]` /
`FICTION_SCOUT["algolia_api_key"]` first; if either is blank, the matching
environment variable is used instead. If both are still blank,
`AlgoliaEngine.__init__` raises `MissingCredentialsError` immediately —
before any network call — rather than letting a doomed request go out. See
[Error handling](#error-handling) below.

You can also inject a pre-built client directly, bypassing credential
resolution entirely (this is what the test suite does):

```python
from algoliasearch.search.client import SearchClientSync
from fiction_scout.engines.algolia import AlgoliaEngine

engine = AlgoliaEngine(client=SearchClientSync("YOUR_APP_ID", "YOUR_ADMIN_KEY"))
```

## Behavior

- `update()` → `save_objects`, with each instance's `to_searchable_array()`
  plus an `objectID` set from `str(adapter.get_scout_key(instance))` —
  always a string, because Algolia requires it, regardless of what type the
  model's own scout key is. Instances whose `to_searchable_array()` is empty
  are excluded from the write rather than sent as empty records.
- `delete()` → `delete_objects`, `flush()` → `clear_objects`. `flush()`
  empties the index but does not delete it — settings survive.
- `search()`/`.get()`/`.paginate()` → one `search_single_index` call per
  query, with `query`, `page`, `hitsPerPage`, and (if any `.where()`s are
  set) `filters` all sent together in a single request — real model
  instances are then fetched back via `adapter.fetch_by_ids`. There is no
  separate "apply filters" step; see
  [Searching: where clauses](../searching.md#where-clauses) for proof this
  isn't a two-step/lazy-ordering issue.
- `create_index()` **raises** `IndexCreationNotSupportedError` — Algolia has
  no explicit index-creation call; an index is created automatically on
  first write. Calling `fiction-scout create-index myapp.models.Post`
  against the `algolia` driver always fails with this error — that's
  expected, not a bug to route around.
- `delete_index()` maps directly to the client's `delete_index`, which
  Algolia does support.
- `.where()`/`.where_in()`/`.where_not_in()` translate into Algolia's
  `filters` syntax — see [Where clauses](#where-clauses) below and
  [Searching: where clauses](../searching.md#where-clauses) for the
  cross-engine translation table.

## Index prefix / multi-tenancy

```python
FICTION_SCOUT = {"driver": "algolia", "index_prefix": f"{tenant_slug}_"}
```

Prepended to every index name this engine resolves (`update`, `delete`,
`flush`, `search`, `delete_index`, `sync-index-settings`). See
[Configuration: multi-tenancy](../configuration.md#multi-tenancy-with-index_prefix).

## Index settings

Each model gets its own Algolia index, and each index needs its own
settings — `attributes_for_faceting` for `Post` almost never matches what
`Author` needs. Settings are therefore nested under
`extra["index_settings"]`, keyed by the model's dotted path (the same path
you pass to `sync-index-settings`):

```python
FICTION_SCOUT = {
    "driver": "algolia",
    "algolia_app_id": "...",
    "algolia_api_key": "...",
    "index_settings": {
        "myapp.models.Post": {
            "searchable_attributes": ["title", "body"],
            "attributes_for_faceting": ["category", "status"],
            "custom_ranking": ["desc(views)"],
        },
        "myapp.models.Author": {
            "attributes_for_faceting": ["country"],
        },
    },
}
```

```bash
fiction-scout sync-index-settings myapp.models.Post
# or, from Django:
python manage.py fiction_scout sync-index-settings myapp.models.Post
```

only ever applies `index_settings["myapp.models.Post"]` to the `Post`
index — `Author`'s settings never leak into it, and vice versa. See
[Configuration: per-model index settings](../configuration.md#per-model-index-settings)
for the full rationale.

`update_index_settings` calls Algolia's `set_settings` with just that
model's entry. The accepted key whitelist is read directly from the
installed `algoliasearch` SDK's own `IndexSettings` pydantic model fields
(the full table below) rather than hand-maintained, so it can't drift out
of sync with whatever SDK version is installed — any key not in that table,
including unrelated entries like `algolia_app_id` or another model's
settings, is silently dropped, not sent.

**Keys are written in this project's snake_case convention**
(`attributes_for_faceting`) and translated to the camelCase Algolia's REST
API actually expects (`attributesForFaceting`) via `IndexSettings`'s own
field aliases before the request goes out — sending snake_case directly on
the wire is rejected by Algolia with `Invalid object attributes:
attributes_for_faceting`. You never need to think about this — just always
write keys in snake_case in `FICTION_SCOUT`, exactly as shown in every
example on this page.

### Full settings reference

Every key below is a real `IndexSettings` field, so every one of them is
accepted by `update_index_settings`/`sync-index-settings`. Grouped by
purpose, snake_case key first (what you write) then the camelCase wire name
(what Algolia's dashboard/docs call it).

#### Searchable attributes & ranking

| Key (snake_case) | Wire name | Type | What it does |
|---|---|---|---|
| `searchable_attributes` | `searchableAttributes` | `list[str]` | Which attributes are searched, and in what priority order — earlier entries rank higher. `"title,alt_title"` (comma, no space) marks two attributes as equal priority; `unordered(title)` disables the "earlier match position ranks higher" rule for that one attribute. |
| `custom_ranking` | `customRanking` | `list[str]` | Tie-breaker ranking criteria applied after Algolia's built-in relevance formula, e.g. `["desc(views)", "asc(price)"]`. |
| `ranking` | `ranking` | `list[str]` | The full ranking formula itself — reorders/replaces Algolia's default criteria order (`typo`, `geo`, `words`, `filters`, `proximity`, `attribute`, `exact`, `custom`). Rarely needed; `custom_ranking` is usually enough. |
| `relevancy_strictness` | `relevancyStrictness` | `int` (0–100) | Relevancy threshold below which less-relevant results (on a virtual replica) are excluded entirely. Default `100` (nothing excluded). |

```python
"index_settings": {
    "myapp.models.Post": {
        "searchable_attributes": ["title,alt_title", "author", "unordered(body)"],
        "custom_ranking": ["desc(views)", "asc(price)"],
        "ranking": ["typo", "geo", "words", "filters", "proximity", "attribute", "exact", "custom"],
        "relevancy_strictness": 90,
    },
},
```

#### Faceting & filtering

| Key (snake_case) | Wire name | Type | What it does |
|---|---|---|---|
| `attributes_for_faceting` | `attributesForFaceting` | `list[str]` | **Required for `.where()`/`.where_in()`/`.where_not_in()` to work at all.** Declares which attributes can be filtered/faceted on. Modifiers: `filterOnly(attr)` (filterable but not returned as a facet), `searchable(attr)` (facet values become searchable too), `afterDistinct(attr)` (facet counts computed after `distinct` dedup). |
| `numeric_attributes_for_filtering` | `numericAttributesForFiltering` | `list[str]` | Restricts which numeric attributes can be used in numeric filters, for faster indexing/smaller index size. `equalOnly(attr)` limits an attribute to `=`/`!=` only (no range queries). Default: all numeric attributes are filterable. |
| `attribute_for_distinct` | `attributeForDistinct` | `str` | The attribute used to group records for `distinct`. |
| `distinct` | `distinct` | `int \| bool` | How many records per `attribute_for_distinct` group to return. `false`/`0` = no dedup (default). `true`/`1` = one (most relevant) per group. `2`–`4` = top N per group. Don't go above `4` — it hurts performance. |
| `max_facet_hits` | `maxFacetHits` | `int` (≤100) | Max facet values returned by `searchForFacetValues`. |
| `max_values_per_facet` | `maxValuesPerFacet` | `int` (≤1000) | Max facet values returned per facet in a normal search response. Default `100`. |
| `sort_facet_values_by` | `sortFacetValuesBy` | `str` | `"count"` (default, most frequent first) or `"alpha"`. |

```python
"index_settings": {
    "myapp.models.Post": {
        "attributes_for_faceting": [
            "category",
            "filterOnly(internal_id)",
            "searchable(tag)",
        ],
        "numeric_attributes_for_filtering": ["equalOnly(status_code)", "views"],
        "attribute_for_distinct": "product_id",
        "distinct": 1,
        "max_values_per_facet": 200,
        "sort_facet_values_by": "count",
    },
},
```

This is the group most relevant to the `UnfilterableAttributeError` fix —
see [Error handling](#error-handling).

#### Typo tolerance

| Key (snake_case) | Wire name | Type | What it does |
|---|---|---|---|
| `typo_tolerance` | `typoTolerance` | `bool \| str` | `true` (default) enables typo tolerance, `false` disables it entirely, `"min"`/`"strict"` tune how aggressively typos are matched. |
| `min_word_sizefor1_typo` | `minWordSizefor1Typo` | `int` | Minimum word length before 1 typo is tolerated. Default `4`. |
| `min_word_sizefor2_typos` | `minWordSizefor2Typos` | `int` | Minimum word length before 2 typos are tolerated. Default `8`. |
| `allow_typos_on_numeric_tokens` | `allowTyposOnNumericTokens` | `bool` | Whether typo tolerance applies to tokens that look numeric (e.g. `"1234"`). Default `true`. |
| `disable_typo_tolerance_on_attributes` | `disableTypoToleranceOnAttributes` | `list[str]` | Attributes exempt from typo tolerance (e.g. SKUs). |
| `disable_typo_tolerance_on_words` | `disableTypoToleranceOnWords` | `list[str]` | Specific words exempt from typo tolerance. |
| `ignore_plurals` | `ignorePlurals` | `bool \| list[str]` | `true` treats singular/plural as equivalent for all supported languages; a list of ISO 639-1 codes scopes it to specific languages. |
| `remove_stop_words` | `removeStopWords` | `bool \| list[str]` | `true` strips stop words (`"the"`, `"a"`, ...) from queries for all languages; a list of ISO codes scopes it. |
| `query_languages` | `queryLanguages` | `list[str]` | ISO 639-1 codes enabling language-specific processing (plurals, stop words) for `ignore_plurals`/`remove_stop_words` when those are `true` rather than an explicit list. |
| `alternatives_as_exact` | `alternativesAsExact` | `list[str]` | Which alternative-match types (`ignorePlurals`, `singleWordSynonym`, `multiWordsSynonym`) still count as an "exact" match for ranking. |

```python
"index_settings": {
    "myapp.models.Post": {
        "typo_tolerance": True,
        "min_word_sizefor1_typo": 4,
        "min_word_sizefor2_typos": 8,
        "disable_typo_tolerance_on_attributes": ["sku"],
        "ignore_plurals": ["en", "es"],
        "remove_stop_words": ["en"],
        "query_languages": ["en"],
        "alternatives_as_exact": ["ignorePlurals", "singleWordSynonym"],
    },
},
```

#### Query strategy

| Key (snake_case) | Wire name | Type | What it does |
|---|---|---|---|
| `query_type` | `queryType` | `str` | `"prefixLast"` (default — only the last word is prefix-matched), `"prefixAll"` (every word), `"prefixNone"` (no prefix matching, exact words only). |
| `remove_words_if_no_results` | `removeWordsIfNoResults` | `str` | Fallback strategy when a query returns zero hits: `"none"` (default, no fallback), `"lastWords"`, `"firstWords"` (drop words from the end/start, up to 5), `"allOptional"` (treat every query word as optional). |
| `advanced_syntax` | `advancedSyntax` | `bool` | Enables `"exact phrase"` and `-excludedWord` query syntax. Default `false`. |
| `advanced_syntax_features` | `advancedSyntaxFeatures` | `list[str]` | Which advanced-syntax features are active: `"exactPhrase"`, `"excludeWords"`. |
| `optional_words` | `optionalWords` | `str \| list[str]` | Words that, if present in the query, are treated as optional rather than required for a match. |
| `disable_exact_on_attributes` | `disableExactOnAttributes` | `list[str]` | Attributes excluded from the "Exact" ranking criterion. |
| `exact_on_single_word_query` | `exactOnSingleWordQuery` | `str` | How "Exact" is computed for a one-word query: `"attribute"` (default, whole attribute must equal the word), `"none"` (criterion ignored), `"word"` (word found anywhere in the attribute, subject to length/stop-word rules). |
| `decompound_query` | `decompoundQuery` | `bool` | Splits compound words (relevant for German/Scandinavian languages configured via `index_languages`). Default `true`. |
| `mode` | `mode` | `str` | `"keywordSearch"` (default, classic text search) or `"neuralSearch"` (vector/semantic search — requires a NeuralSearch-enabled index). |
| `semantic_search` | `semanticSearch` | `dict` | Configuration for `mode: "neuralSearch"`, e.g. `{"eventSources": ["source1"]}`. |
| `enable_rules` | `enableRules` | `bool` | Whether Algolia Rules (merchandising) are applied. Default `true`. |
| `enable_personalization` | `enablePersonalization` | `bool` | Whether Algolia Personalization affects ranking. Default `false`. |

```python
"index_settings": {
    "myapp.models.Post": {
        "query_type": "prefixLast",
        "remove_words_if_no_results": "lastWords",
        "advanced_syntax": True,
        "optional_words": ["the", "a"],
        "exact_on_single_word_query": "word",
        "enable_rules": True,
        "enable_personalization": False,
    },
},
```

#### Highlighting & snippeting

| Key (snake_case) | Wire name | Type | What it does |
|---|---|---|---|
| `attributes_to_highlight` | `attributesToHighlight` | `list[str]` | Which attributes get `_highlightResult` markup in responses. Defaults to `searchable_attributes` if unset. |
| `attributes_to_snippet` | `attributesToSnippet` | `list[str]` | Attributes to truncate around the match, e.g. `"body:20"` for a 20-word snippet. |
| `highlight_pre_tag` | `highlightPreTag` | `str` | Opening tag wrapping a highlighted match. Default `"<em>"`. |
| `highlight_post_tag` | `highlightPostTag` | `str` | Closing tag. Default `"</em>"`. |
| `snippet_ellipsis_text` | `snippetEllipsisText` | `str` | Text inserted where a snippet was truncated. Default `"…"`. |
| `restrict_highlight_and_snippet_arrays` | `restrictHighlightAndSnippetArrays` | `bool` | If `true`, array attributes only return highlighted/snippeted entries that actually matched, not the whole array. Default `false`. |
| `replace_synonyms_in_highlight` | `replaceSynonymsInHighlight` | `bool` | Whether a highlighted word is replaced with the synonym that actually matched. Default `false`. |

```python
"index_settings": {
    "myapp.models.Post": {
        "attributes_to_highlight": ["title", "body"],
        "attributes_to_snippet": ["body:20"],
        "highlight_pre_tag": "<mark>",
        "highlight_post_tag": "</mark>",
        "snippet_ellipsis_text": "…",
    },
},
```

#### Pagination & response shape

| Key (snake_case) | Wire name | Type | What it does |
|---|---|---|---|
| `hits_per_page` | `hitsPerPage` | `int` | Default page size when a search doesn't specify one. fiction-scout's own `.paginate(per_page, page)` always passes an explicit `hitsPerPage`, so this setting only affects `.raw()` calls or direct client use that omit it. |
| `pagination_limited_to` | `paginationLimitedTo` | `int` | Hard cap on how deep pagination can go (`page * hitsPerPage`), for performance. Default `1000`. |
| `attributes_to_retrieve` | `attributesToRetrieve` | `list[str]` | Which attributes are returned per hit. `["*"]` (default) returns everything. |
| `response_fields` | `responseFields` | `list[str]` | Which top-level response fields (`hits`, `nbHits`, `page`, ...) are returned. `["*"]` (default) returns everything. |
| `unretrievable_attributes` | `unretrievableAttributes` | `list[str]` | Attributes that are indexed/searchable but never returned in results (e.g. an internal `total_sales` figure). |

```python
"index_settings": {
    "myapp.models.Post": {
        "attributes_to_retrieve": ["title", "body", "author"],
        "unretrievable_attributes": ["internal_score"],
        "pagination_limited_to": 1000,
    },
},
```

#### Language & normalization

| Key (snake_case) | Wire name | Type | What it does |
|---|---|---|---|
| `index_languages` | `indexLanguages` | `list[str]` | ISO 639-1 codes for languages actually present in the index — improves plural/segmentation handling for those languages (e.g. `["ja"]` for Japanese word segmentation). |
| `camel_case_attributes` | `camelCaseAttributes` | `list[str]` | Attributes whose camelCase words (`iPhone13`) should be split for indexing. |
| `decompounded_attributes` | `decompoundedAttributes` | `dict[str, list[str]]` | Per-language compound-word splitting, e.g. `{"de": ["name"]}` for German. |
| `disable_prefix_on_attributes` | `disablePrefixOnAttributes` | `list[str]` | Attributes exempt from prefix search (e.g. exact-match-only SKU fields). |
| `separators_to_index` | `separatorsToIndex` | `str` | Extra characters treated as significant for indexing rather than stripped, e.g. `"+#"` so `"C++"`/`"C#"` are searchable. |
| `keep_diacritics_on_characters` | `keepDiacriticsOnCharacters` | `str` | Characters whose diacritics are preserved rather than normalized away, e.g. `"øé"`. |
| `custom_normalization` | `customNormalization` | `dict[str, dict[str, str]]` | Custom character-normalization map, e.g. `{"default": {"ä": "ae", "ü": "ue"}}`. |
| `attributes_to_transliterate` | `attributesToTransliterate` | `list[str]` | Attributes converted to Latin script for matching (e.g. Cyrillic → Latin). |

```python
"index_settings": {
    "myapp.models.Post": {
        "index_languages": ["en"],
        "separators_to_index": "+#",
        "disable_prefix_on_attributes": ["sku"],
    },
},
```

#### Ranking internals & merchandising

| Key (snake_case) | Wire name | Type | What it does |
|---|---|---|---|
| `min_proximity` | `minProximity` | `int` (1–7) | The proximity ranking criterion stops distinguishing between query-word distances beyond this value. Default `1`. |
| `attribute_criteria_computed_by_min_proximity` | `attributeCriteriaComputedByMinProximity` | `bool` | Whether the "attribute" ranking criterion also respects `min_proximity`. Default `false`. |
| `rendering_content` | `renderingContent` | `dict` | Merchandising metadata for the search UI — facet ordering, banners, redirects. Passed through to the response, not interpreted by fiction-scout. |
| `enable_re_ranking` | `enableReRanking` | `bool` | Whether Dynamic Re-Ranking is active (requires it to be enabled for the index in the Algolia dashboard first). Default `true` once enabled. |
| `re_ranking_apply_filter` | `reRankingApplyFilter` | `list` | Restricts Dynamic Re-Ranking to results matching these filters. |

#### Miscellaneous

| Key (snake_case) | Wire name | Type | What it does |
|---|---|---|---|
| `replicas` | `replicas` | `list[str]` | Replica indices kept in sync with this one, for alternate ranking/sort orders. `virtual(name)` creates a virtual (no extra storage) replica. fiction-scout doesn't manage replica indices itself — this just configures Algolia's side. |
| `allow_compression_of_integer_array` | `allowCompressionOfIntegerArray` | `bool` | Whether integer arrays are compressed for smaller index size (trades a small amount of performance). |
| `user_data` | `userData` | `dict` | Arbitrary metadata stored alongside index settings — never interpreted by Algolia or fiction-scout, purely for your own bookkeeping. |

### Every setting at once

Combining most of the above into one model, mirroring Algolia's own
[settings API reference example](https://www.algolia.com/doc/rest-api/search/set-settings)
translated into fiction-scout's snake_case convention:

```python
FICTION_SCOUT = {
    "driver": "algolia",
    "algolia_app_id": "...",
    "algolia_api_key": "...",
    "index_settings": {
        "myapp.models.Post": {
            "searchable_attributes": ["title,alt_title", "author", "unordered(body)"],
            "attributes_for_faceting": ["category", "filterOnly(internal_id)"],
            "custom_ranking": ["desc(views)", "asc(price)"],
            "numeric_attributes_for_filtering": ["equalOnly(status_code)"],
            "attribute_for_distinct": "product_id",
            "distinct": 1,
            "max_values_per_facet": 200,
            "sort_facet_values_by": "count",
            "typo_tolerance": True,
            "min_word_sizefor1_typo": 4,
            "min_word_sizefor2_typos": 8,
            "ignore_plurals": ["en"],
            "remove_stop_words": ["en"],
            "query_type": "prefixLast",
            "remove_words_if_no_results": "lastWords",
            "advanced_syntax": True,
            "attributes_to_highlight": ["title", "body"],
            "attributes_to_snippet": ["body:20"],
            "highlight_pre_tag": "<em>",
            "highlight_post_tag": "</em>",
            "attributes_to_retrieve": ["*"],
            "unretrievable_attributes": ["internal_score"],
            "index_languages": ["en"],
            "min_proximity": 1,
            "replicas": ["virtual(posts_price_asc)"],
        },
    },
}
```

## Where clauses

`.where()`/`.where_in()`/`.where_not_in()` compile to Algolia's `filters`
string syntax, built by `AlgoliaEngine._filters()` — mirroring Laravel
Scout's `AlgoliaEngine::filters()` exactly.

| fiction-scout | Algolia `filters` |
|---|---|
| `.where("status", "published")` | `status:'published'` |
| `.where_in("category", ["a", "b"])` | `(category:'a' OR category:'b')` |
| `.where_in("category", [])` | `0:1` (always-false sentinel — Algolia's own convention) |
| `.where_not_in("category", ["c"])` | `(NOT category:'c')` |
| `.where_not_in("category", [])` | *(no clause added)* |
| `.where("a", 1).where_in("b", ["x"])` | `a:'1' AND (b:'x')` — every clause is `AND`-joined |

```python
# Single equality filter
Post.search("django").where("status", "published").get()

# Combined filters — all AND-joined
Post.search("django").where("status", "published").where_in("category", ["tech", "news"]).get()

# Exclude a set of values
Post.search("django").where_not_in("category", ["spam"]).get()

# Filter with no search term (pure filtering, no relevance ranking beyond it)
Post.search().where("author_id", 42).get()

# .paginate() and .raw() accept the same where-clauses
Post.search("django").where("status", "published").paginate(per_page=20, page=2)
```

Every value is wrapped in single quotes (`field:'value'`) regardless of
its Python type — this mirrors Laravel Scout's own implementation
one-for-one. **The field must be declared in `attributes_for_faceting`**
(see above) or the request is rejected — see the next section.

## Error handling

Every `AlgoliaEngine` method that talks to the network routes through
`_translate_client_errors()`, which turns raw SDK/network failures into
one of fiction-scout's own exceptions (all subclasses of
`FictionScoutError`, importable from `fiction_scout.exceptions`) with a
concrete hint for how to fix it, instead of leaking a bare
`algoliasearch`/`requests`/`urllib3` traceback.

| Exception | Raised when | Example trigger |
|---|---|---|
| `MissingCredentialsError` | `AlgoliaEngine()` constructed with no `app_id`/`api_key` and none found in the `ALGOLIA_APP_ID`/`ALGOLIA_API_KEY` env vars either. Raised in `__init__`, before any client is built. | Running `seed_movies` with a fresh `.env` that was never filled in. |
| `EngineAuthenticationError` | The API responds `401`/`403` — the app id resolved, but the key is wrong or lacks the required ACL. | Using a search-only public key for a write operation. |
| `EngineConnectionError` | A `requests.exceptions.ConnectionError` or the SDK's own `AlgoliaUnreachableHostException` — typically DNS resolution failure. | A **wrong `algolia_app_id`** — Algolia builds the request hostname from the app id, so a typo'd id fails DNS resolution and looks like a network outage, not an auth error. This is the single most common cause. |
| `UnfilterableAttributeError` | The API responds `400` naming `attributesForFaceting` — a `.where()`/`.where_in()`/`.where_not_in()` field isn't declared filterable on that index. | `Movie.search().where("release_year", 2000).get()` before running `sync-index-settings` for that field. |

Every other error (e.g. a plain `400` with no faceting hint, a `404`) is
re-raised unchanged as the original `algoliasearch` exception — only the
specific, actionable cases above get translated.

```python
from fiction_scout.exceptions import (
    EngineAuthenticationError,
    EngineConnectionError,
    MissingCredentialsError,
    UnfilterableAttributeError,
)

try:
    Movie.search().where("release_year", 1999).get()
except UnfilterableAttributeError as exc:
    # "The 'algolia' driver rejected a filter: ... A field passed to
    #  .where()/.where_in()/.where_not_in() must be listed in this index's
    #  'attributes_for_faceting' setting. Add it under this model's entry
    #  in FICTION_SCOUT['extra']['index_settings'] ..."
    print(exc)
```

`IndexCreationNotSupportedError` (raised by `create_index()`, always — not
network-dependent) and `IndexSettingsNotSupportedError` (raised by drivers
with no settings API at all — never actually happens for `algolia`, which
does support settings) round out the exceptions this engine can raise.

## Known v1 limitations

- **Soft-deleted records are removed from the index entirely**, not tagged
  and kept — `with_trashed()`/`only_trashed()` only work against the
  `database`/`collection` engines. See
  [Indexing: soft delete](../indexing.md#soft-delete).
- **No async variant.** Only `SearchClientSync` is used; `algoliasearch`
  also ships an async client, but fiction-scout doesn't wire it up (see
  `sync/context.py`'s `contextvars` hook, reserved for future async work).

## Testing

`AlgoliaEngine(client=...)` accepts an injectable client, which is what the
project's own test suite uses — a hand-rolled fake client
(`tests/support.py`'s `FakeAlgoliaClient`), not `unittest.mock` or a live
Algolia account (Algolia has no self-hosted mode). The fake supports an
injectable `raises=` fault to simulate wire-boundary failures
(`RequestException`, `AlgoliaUnreachableHostException`,
`requests.exceptions.ConnectionError`) without a live account. See
`src/fiction_scout/engines/algolia.py`'s module docstring for the full
rationale.

```python
from algoliasearch.http.exceptions import RequestException
from fiction_scout.engines.algolia import AlgoliaEngine
from tests.support import FakeAlgoliaClient

# Happy path
client = FakeAlgoliaClient(search_hits=[...], nb_hits=1)
engine = AlgoliaEngine(client=client)

# Simulated failure
client = FakeAlgoliaClient(raises=RequestException("Invalid API key", 401))
engine = AlgoliaEngine(client=client)
```
