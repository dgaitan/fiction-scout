# `algolia` engine

Talks to Algolia's SaaS index API via the official `algoliasearch` client.

```bash
pip install "fiction-scout[algolia]"
```

```python
FICTION_SCOUT = {
    "driver": "algolia",
    "algolia_app_id": "...",   # or set the ALGOLIA_APP_ID env var
    "algolia_api_key": "...",  # or set the ALGOLIA_API_KEY env var
}
```

## Behavior

- `update()` → `save_objects`, with each instance's `to_searchable_array()`
  plus an `objectID` set from `str(adapter.get_scout_key(instance))` —
  always a string, because Algolia requires it, regardless of what type the
  model's own scout key is. Instances whose `to_searchable_array()` is empty
  are excluded from the write rather than sent as empty records.
- `delete()` → `delete_objects`, `flush()` → `clear_objects`.
- `search()`/`.get()` → `search_single_index`, then real model instances are
  fetched back via `adapter.fetch_by_ids`.
- `create_index()` **raises** `IndexCreationNotSupportedError` — Algolia has
  no explicit index-creation call; an index is created automatically on
  first write. This mirrors Laravel Scout's own
  `AlgoliaEngine::createIndex()`, which throws for the same reason.
- `delete_index()` maps directly to the client's `delete_index`, which
  Algolia does support.

## Known v1 limitations

- **`Builder.where()`/`.where_in()`/`.where_not_in()` are not translated**
  into Algolia's `filters`/`facetFilters` syntax — a `.where()` call against
  this driver returns unfiltered results, not an error.
- **Soft-deleted records are removed from the index entirely**, not tagged
  and kept — `with_trashed()`/`only_trashed()` only work against the
  `database` engine.

## Testing

`AlgoliaEngine(client=...)` accepts an injectable client, which is what the
project's own test suite uses — a hand-rolled fake client, not
`unittest.mock` or a live Algolia account (Algolia has no self-hosted mode).
See `src/fiction_scout/engines/algolia.py`'s module docstring for the full
rationale.
