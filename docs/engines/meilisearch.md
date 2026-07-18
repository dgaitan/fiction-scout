# `meilisearch` engine

Talks to a self-hosted or embedded Meilisearch server via the official
`meilisearch` client.

```bash
pip install "fiction-scout[meilisearch]"
```

```python
FICTION_SCOUT = {
    "driver": "meilisearch",
    "meilisearch_url": "http://127.0.0.1:7700",  # or set MEILISEARCH_URL
    "meilisearch_api_key": "...",                  # or set MEILISEARCH_API_KEY
}
```

## Behavior

- `update()` → `index.add_documents`, with the model's primary key passed
  explicitly (`adapter.get_scout_key_name(model)`) — unlike Algolia,
  Meilisearch preserves the scout key's original type (int, string,
  whatever the model uses) rather than coercing it.
- `delete()` → `index.delete_documents(ids=...)`, `flush()` →
  `index.delete_all_documents()` — flush empties the index but does **not**
  delete it: searchable attributes and ranking rules configured on the
  index survive a flush. (This "empty, don't destroy" contract is shared
  with Algolia's `clear_objects`, but not every engine — a future
  Elasticsearch driver's `flush` needs the same care, since a naive index
  delete+recreate would also drop mapping settings.)
- `search()`/`.get()` → `index.search(term)`, then real model instances are
  fetched back via `adapter.fetch_by_ids`.
- `create_index()` is a **real, idempotent get-or-create** — the one place
  this engine's shape diverges from Algolia's. It fetches the index by name
  first and only calls the create endpoint if missing, then waits for that
  creation task to finish before returning (idempotency is meaningless
  without the completion guarantee: two `create_index()` calls issued
  back-to-back without waiting could both see "not found" and the second
  would error). `update`/`delete`/`flush` do not wait for their tasks.
- Searching a model that has never been synced raises `index_not_found` at
  the Meilisearch API level rather than returning empty results — this
  engine catches that specific error and returns zero results instead of
  propagating it, so an unsynced model behaves like an empty index rather
  than an error.
- `.where()`/`.where_in()`/`.where_not_in()` translate into Meilisearch's
  `filter` syntax — see [Searching: where clauses](../searching.md#where-clauses)
  for the full translation table, including value-type handling
  (bool/`None`/numeric/string). Filtering by a field requires that field to
  be listed in that index's `filterableAttributes` first — see "Index
  settings" below.

## Index settings

```python
FICTION_SCOUT = {
    "driver": "meilisearch",
    "meilisearch_url": "http://127.0.0.1:7700",
    "meilisearch_api_key": "...",
    "filterable_attributes": ["category", "status"],
    "sortable_attributes": ["views"],
}
```

```bash
fiction-scout create-index myapp.models.Post   # only needed before the first sync
fiction-scout sync-index-settings myapp.models.Post
```

`update_index_settings` calls `index.update_settings`. Config keys use this
project's snake_case convention (`filterable_attributes`,
`sortable_attributes`, `searchable_attributes`, `ranking_rules`,
`distinct_attribute`, `stop_words`, `synonyms`, `typo_tolerance`,
`pagination`, `faceting`, `embedders`, and a handful more — see
`_MEILISEARCH_SETTINGS_KEYS` in `engines/meilisearch.py` for the exact list)
and get mapped to the camelCase keys Meilisearch's REST API expects. Any
other key present in `config.extra` — including unrelated connection
settings like `algolia_app_id` — is silently ignored rather than sent. Waits
for the settings task to finish before returning, same as `create_index`.

## Known v1 limitations

- **Soft-deleted records are removed from the index entirely**, not tagged
  and kept — `with_trashed()`/`only_trashed()` only work against the
  `database`/`collection` engines. See
  [Indexing: soft delete](../indexing.md#soft-delete).

## Testing

Unlike Algolia, Meilisearch ships as a single binary with an official Docker
image, so it's genuinely testable without mocking. The project's test suite
runs a mocked-client tier unconditionally, plus a live-server tier that
launches the `meilisearch` binary as a subprocess (if it's on `PATH`) or
connects to `MEILISEARCH_TEST_URL` — skipped gracefully, not failed, when
neither is available. See `src/fiction_scout/engines/meilisearch.py`'s
module docstring for the full rationale.
