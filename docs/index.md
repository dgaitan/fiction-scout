# fiction-scout

A driver-based full-text search layer that auto-syncs your models to a
search index, inspired by [Laravel Scout](https://laravel.com/docs/master/scout).
Add a mixin to a model, and fiction-scout keeps its search index up to date
using your ORM's own change-tracking mechanism — no polling, no manual
bookkeeping.

## What's built today

- **Core** — the `Engine` contract, `EngineManager`, the fluent search
  `Builder`, `FictionScoutConfig` resolution (Django settings → Flask app
  config → environment variables → defaults), and `without_syncing_to_search`
  for pausing auto-sync around bulk operations.
- **`database`** and **`collection`** engines — no external service required.
  See [Engines](engines/database.md).
- **Django ORM adapter** — signal-based auto-sync
  (`fiction_scout.adapters.django.SearchableMixin`).
- **Standalone CLI** (`fiction-scout import|queue-import|flush|sync-index-settings`)
  and a Django management command bridge (`manage.py fiction_scout ...`) that
  wrap the exact same underlying functions.
- **Celery dispatcher** — background indexing via the `Dispatcher` protocol.
- **Algolia** and **Meilisearch** engines — see [Engines](engines/algolia.md).

**Not built yet:** a SQLAlchemy adapter and an Elasticsearch engine. Both
have extension points already in place (`SearchableAdapter`, `Engine`) —
see [Extending: custom adapters](extending/custom-adapters.md) and
[Extending: custom drivers](extending/custom-drivers.md) — but neither ships
today. Installing `fiction-scout[sqlalchemy]` or configuring the
`elasticsearch` driver will not work until they land.

## Installation

```bash
pip install "fiction-scout[django]"       # Django projects
pip install "fiction-scout[algolia]"      # optional: Algolia search engine
pip install "fiction-scout[meilisearch]"  # optional: Meilisearch search engine
pip install "fiction-scout[celery]"       # optional: background indexing via Celery
```

## Quickstart (Django)

```python
# settings.py
INSTALLED_APPS = [..., "fiction_scout.adapters.django"]
FICTION_SCOUT = {"driver": "database"}
```

```python
# models.py
from django.db import models
from fiction_scout.adapters.django.mixin import SearchableMixin


class Post(SearchableMixin, models.Model):
    title = models.CharField(max_length=255)
    body = models.TextField()


results = Post.search("Star Trek").get()
```

A complete, runnable version of this is in
[`examples/django_example/`](https://github.com/davidgaitan/fiction-scout/tree/main/examples/django_example).

## The `Searchable` mixin's public surface

Every ORM adapter's mixin exposes the same methods:

| Method | Purpose |
|---|---|
| `Model.search(term)` | Returns a `Builder` — call `.get()`, `.paginate()`, or `.raw()` on it |
| `instance.searchable()` | Push one instance to the index immediately |
| `instance.unsearchable()` | Remove one instance from the index immediately |
| `instance.to_searchable_array()` | The dict of data actually sent to the index — override to control what's searchable |
| `instance.should_be_searchable()` | Override to exclude an instance from indexing based on app logic |

`Builder` supports `.where(field, value)`, `.where_in(field, values)`,
`.where_not_in(field, values)`, `.within(index_name)`, `.with_trashed()`,
`.only_trashed()`, and `.query(callback)` for further customizing the
fetch-matched-models query. `where`/`where_in`/`where_not_in` and
`with_trashed`/`only_trashed` are honored by the `database` engine only —
external engines (Algolia, Meilisearch) fetch matches by scout key and don't
translate these into their own filter syntax yet.

## Configuration

`FICTION_SCOUT` (Django settings, Flask app config, or a `FICTION_SCOUT_*`
environment variable prefix) accepts:

| Key | Default | Meaning |
|---|---|---|
| `driver` | `"database"` | Which registered `Engine` to use — `database`, `collection`, `algolia`, `meilisearch`, or a name registered via `EngineManager.extend()` |
| `soft_delete` | `False` | Whether soft-deleted records should be excluded by default |
| `chunk_size` | `500` | Batch size for `chunk_records`/bulk sync operations |
| `queue` | `False` | Whether to route sync writes through a background `Dispatcher` |
| `index_prefix` | `""` | Prefix applied to index/table names |
| anything else | — | Driver-specific settings (e.g. `algolia_app_id`, `meilisearch_url`) land in `FictionScoutConfig.extra` |

## Pausing sync

```python
from fiction_scout.sync.context import without_syncing_to_search

with without_syncing_to_search():
    Post.objects.bulk_create([...])  # no per-row sync while this runs
```

## Soft delete

Declare `soft_delete_field` on a model (a `ClassVar[str | None]`, defaulting
to `None`). When that field is truthy on save, the instance is removed from
the index rather than updated. `Builder.with_trashed()`/`.only_trashed()`
only work against the `database` engine in v1 — external engines never keep
soft-deleted records in-index, so there's nothing for those flags to find
there.

## CLI

```bash
fiction-scout import myapp.models.Post              # push every existing row
fiction-scout queue-import myapp.models.Post         # same, via the configured dispatcher
fiction-scout flush myapp.models.Post                # remove all index entries, leave rows alone
fiction-scout sync-index-settings myapp.models.Post  # apply driver-specific index settings
```

Under Django, the same four subcommands are available as
`manage.py fiction_scout <subcommand> <dotted.model.Path>` — it calls the
identical underlying functions, just with Django's own argument parsing.

## Extending

- [Adding a search driver](extending/custom-drivers.md) — implement `Engine`,
  register it with `EngineManager.extend()`.
- [Adding an ORM adapter](extending/custom-adapters.md) — implement
  `SearchableAdapter` and `ScoutModel` for a new ORM.
