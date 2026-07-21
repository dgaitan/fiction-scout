# Configuration

`FictionScoutConfig` is resolved once per process and shared by every
searchable model. Resolution order (`fiction_scout.config.resolve_config`):

1. An explicitly-constructed `FictionScoutConfig` passed in code — always
   wins outright.
2. Django settings — a `FICTION_SCOUT = {...}` dict in `settings.py`.
3. Flask app config — `app.config["FICTION_SCOUT"] = {...}`.
4. Environment variables — `FICTION_SCOUT_DRIVER`, `FICTION_SCOUT_SOFT_DELETE`,
   `FICTION_SCOUT_CHUNK_SIZE`, `FICTION_SCOUT_QUEUE`,
   `FICTION_SCOUT_INDEX_PREFIX`.
5. Bare defaults, if nothing above applies.

The first resolver that finds applicable settings wins; nothing lower in the
list runs. SQLAlchemy has no settings-style resolver of its own (there's no
`sessionmaker`-adjacent config object to read `FICTION_SCOUT` off of) — pass
an explicit `FictionScoutConfig` to `runtime.configure(session_factory=...,
config=...)`, or fall back to the `FICTION_SCOUT_*` environment variables.

## Fields

| Key | Default | Meaning |
|---|---|---|
| `driver` | `"database"` | Which registered `Engine` to use — `database`, `collection`, `algolia`, `meilisearch`, or a name registered via `EngineManager.extend()`. |
| `chunk_size` | `500` | Batch size for `chunk_records`/bulk sync operations (`import`, signal-triggered auto-sync). |
| `index_prefix` | `""` | Prepended to every index name **on external-index drivers only** (`algolia`, `meilisearch`). Lets multiple tenants/environments share one Algolia application or Meilisearch server without index-name collisions. Has no effect on `database`/`collection`, which query real DB tables by their real names, not a resolved "index name." An explicit `.within("some_index")` call bypasses the prefix entirely, same as it bypasses `searchable_as()` — see [Searching](searching.md). |
| `extra` | `{}` | Anything not in the fields above lands here — driver-specific settings (`algolia_app_id`, `meilisearch_url`, index-settings keys — see below) all live in this one flat dict. |
| `soft_delete` | `False` | **Parsed, currently unused.** fiction-scout doesn't implement a "keep soft-deleted records tagged in-index" behavior gated by this flag (see [Indexing: soft delete](indexing.md#soft-delete)) — what actually gates soft-delete behavior per model is the model's own `soft_delete_field` class variable, not this config key. |
| `queue` | `False` | **Parsed, currently unused.** Nothing reads this field to auto-select a dispatcher — `runtime.get_dispatcher()` always returns a synchronous `SyncDispatcher()` for both the Django and SQLAlchemy adapters. To run sync operations through Celery instead, construct a `CeleryDispatcher` yourself and use the standalone CLI's `queue-import`, or wire it into your own adapter's `get_scout_dispatcher()`. |

## Driver-specific `extra` keys

```python
FICTION_SCOUT = {
    "driver": "algolia",
    "algolia_app_id": "...",        # or ALGOLIA_APP_ID env var
    "algolia_api_key": "...",       # or ALGOLIA_API_KEY env var
}
```

```python
FICTION_SCOUT = {
    "driver": "meilisearch",
    "meilisearch_url": "http://127.0.0.1:7700",  # or MEILISEARCH_URL env var
    "meilisearch_api_key": "...",                # or MEILISEARCH_API_KEY env var
}
```

## Per-model index settings

Connection keys (`algolia_app_id`, `meilisearch_url`, etc.) are genuinely
global — one Algolia application or Meilisearch server per process. Index
settings (`searchable_attributes`, `filterable_attributes`,
`attributes_for_faceting`, `custom_ranking`, etc.) are **not** global — each
model has its own index with its own fields, so they're nested under
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
            "attributes_for_faceting": ["category"],
        },
        "myapp.models.Author": {
            "attributes_for_faceting": ["country"],
        },
    },
}
```

```bash
fiction-scout sync-index-settings myapp.models.Post
```

only applies `index_settings["myapp.models.Post"]` — `Author`'s settings
never reach `Post`'s index, and vice versa. Each engine's `update_index_settings`
still whitelists only the keys it recognizes from that model's own entry
and silently drops the rest — see each engine's "Index settings" section
([algolia](engines/algolia.md#index-settings),
[meilisearch](engines/meilisearch.md#index-settings)) for the full accepted
key list per driver. A model with no entry in `index_settings` is a no-op,
same as having no relevant keys at all.

## Multi-tenancy with `index_prefix`

```python
FICTION_SCOUT = {
    "driver": "meilisearch",
    "index_prefix": f"{tenant_slug}_",
}
```

Every index name Algolia/Meilisearch resolve for a model —
on `update()`, `delete()`, `flush()`, `search()`, `create_index()` (via the
`create-index` CLI command), and `sync-index-settings` — gets this prefix
prepended. A single Algolia application or Meilisearch server can then host
multiple tenants' indexes side by side (`tenant_a_articles`,
`tenant_b_articles`, ...) without collisions.
