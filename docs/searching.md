# Searching

`Model.search(term)` returns a `Builder` — a fluent object that accumulates
constraints and only actually queries the engine when you call `.get()`,
`.paginate()`, or `.raw()`.

```python
results = Post.search("Star Trek").get()   # list of Post instances
```

## Where clauses

```python
Post.search("Star Trek") \
    .where("status", "published") \
    .where_in("category", ["scifi", "action"]) \
    .where_not_in("category", ["horror"]) \
    .get()
```

`.where()` only ever expresses equality (there's no 3-arg operator form).

**The field name means something different depending on the engine — this
is the most common source of confusion with where clauses:**

| Engine | `field` resolves against |
|---|---|
| `database` | The real ORM query, exactly as if you'd written it by hand — including relation-traversal syntax. **Not** `to_searchable_array()` keys. |
| `collection` | The literal keys of the dict returned by `to_searchable_array()` — matching happens against that dict in Python, nothing else. |
| `algolia` / `meilisearch` | Also the keys of `to_searchable_array()`, since that's what got pushed to the index — translated into each driver's native filter syntax below. |

Concretely: given a Django model with `director = models.ForeignKey(Director, ...)`
and `to_searchable_array()` returning `{"director": self.director.name}`,
`.where_in("director", [...])` only works on `collection`/`algolia`/
`meilisearch`. On `database`, Django resolves `director__in` against the
literal `director` field — the FK column, an integer id — not the related
`Director.name`. You need `.where_in("director__name", [...])` instead, the
same relation-traversal syntax you'd use in a raw
`Movie.objects.filter(director__name__in=[...])` call. See
[`database`'s own notes on this](engines/database.md#where-clause-fields-are-real-query-paths)
for the full explanation.

On `algolia`/`meilisearch`, `.where()`/`.where_in()`/`.where_not_in()`
translate into each driver's native filter syntax:

| fiction-scout | Algolia `filters` | Meilisearch `filter` |
|---|---|---|
| `.where("status", "published")` | `status:'published'` | `status = "published"` |
| `.where_in("category", ["a", "b"])` | `(category:'a' OR category:'b')` | `category IN ["a", "b"]` |
| `.where_not_in("category", ["c"])` | `(NOT category:'c')` | `category NOT IN ["c"]` |

An empty `.where_in(field, [])` against Algolia becomes the `'0:1'`
always-false sentinel (matching Algolia's own convention); against
Meilisearch it becomes `field IN []`, which is valid and also always false
— no sentinel needed there.

**Filtering by a field requires that field to actually be filterable on the
engine's side first.** Meilisearch rejects a filter on a field that isn't in
that index's `filterableAttributes`; Algolia requires the field to be listed
in `attributesForFaceting`. Both engines raise fiction-scout's own
`UnfilterableAttributeError` (not a raw SDK exception) when this happens,
naming the field and pointing at the fix. See each engine's "Index
settings" section ([algolia](engines/algolia.md#index-settings),
[meilisearch](engines/meilisearch.md#index-settings)) to configure that.

## Custom index

```python
Post.search("Star Trek").within("archived_posts").get()
```

Overrides which index gets queried, bypassing `searchable_as()` — and, on
`algolia`/`meilisearch`, bypassing `FictionScoutConfig.index_prefix` too,
since the literal name you pass is used as-is.

## Customizing the fetched-records query

```python
Post.search("Star Trek").query(lambda qs: qs.select_related("author")).get()
```

On the `database` engine, this callback's constraints apply directly to the
query used to *find* matches, so it can filter results too. On every other
engine (`collection`, `algolia`, `meilisearch`), matching records are already
determined by the search index before this callback ever runs — it only
customizes how the matched rows get fetched back (eager-loading a relation,
for instance), and any filtering inside it has no effect on which records
matched.

## Pagination

```python
page = Post.search("Star Trek").paginate(per_page=15, page=2)

page.items       # the matched Post instances for this page
page.total       # total match count across all pages
page.has_more    # whether a page after this one exists
len(page)        # == len(page.items)
for post in page:  # Page is iterable
    ...
```

## Raw results

```python
raw = Post.search("Star Trek").raw()
```

Returns the engine's unprocessed, driver-specific result object — an
Algolia/Meilisearch response object, an unexecuted query wrapper for
`database`, or a list of matched searchable-array dicts for `collection` —
with no model hydration. Useful for inspecting what an engine actually
returned (facet counts, highlight snippets, `_rankingInfo`) before it's
reduced to plain model instances.
