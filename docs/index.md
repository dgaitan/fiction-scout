# fiction-scout

A driver-based full-text search layer that auto-syncs your models to a
search index. Add a mixin to a model, and fiction-scout keeps its search
index up to date using your ORM's own change-tracking mechanism — no
polling, no manual bookkeeping.

## What's built today

- **Core** — the `Engine` contract, `EngineManager`, the fluent search
  `Builder`, `FictionScoutConfig` resolution (Django settings → Flask app
  config → environment variables → defaults), and `without_syncing_to_search`
  for pausing auto-sync around bulk operations.
- **`database`** and **`collection`** engines — no external service required.
  See [Engines](engines/database.md).
- **Django ORM adapter** — signal-based auto-sync
  (`fiction_scout.adapters.django.mixin.SearchableMixin`).
- **SQLAlchemy adapter** — session-event auto-sync via `before_commit`/
  `after_commit` (`fiction_scout.adapters.sqlalchemy.mixin.SearchableMixin`).
  Unlike Django, there's no settings-style implicit registry to discover a
  connection from — call `fiction_scout.adapters.sqlalchemy.runtime.configure(session_factory=...)`
  once at startup.
- **Standalone CLI** (`fiction-scout import|queue-import|flush|sync-index-settings`)
  and a Django management command bridge (`manage.py fiction_scout ...`) that
  wrap the exact same underlying functions.
- **Celery dispatcher** — background indexing via the `Dispatcher` protocol.
- **Algolia** and **Meilisearch** engines — see [Engines](engines/algolia.md).

**Not built yet:** an Elasticsearch engine. It has an extension point
already in place (`Engine`) — see
[Extending: custom drivers](extending/custom-drivers.md) — but doesn't ship
today. Configuring the `elasticsearch` driver will not work until it lands.

## Installation

```bash
pip install "fiction-scout[django]"       # Django projects
pip install "fiction-scout[sqlalchemy]"   # SQLAlchemy / Flask-SQLAlchemy projects
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

## Quickstart (SQLAlchemy)

SQLAlchemy has no settings-style implicit registry to auto-discover a
database connection from — call `runtime.configure()` once at startup with
your `sessionmaker`. This is also what wires up the `before_commit`/
`after_commit` auto-sync hooks (the SQLAlchemy equivalent of Django's
`post_save`/`post_delete` signals — see [Indexing](indexing.md) for why the
two mechanisms are deliberately different, not just differently spelled).

```python
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from fiction_scout.adapters.sqlalchemy import runtime
from fiction_scout.adapters.sqlalchemy.mixin import SearchableMixin


class Base(DeclarativeBase):
    pass


class Post(SearchableMixin, Base):
    __tablename__ = "posts"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str]
    body: Mapped[str]


Session = sessionmaker(bind=engine)
runtime.configure(session_factory=Session)

with Session() as session:
    post = Post(title="Star Trek II", body="The Wrath of Khan")
    session.add(post)
    session.commit()  # synced to the index only once the transaction lands

results = Post.search("Star Trek").get()
```

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
environment variable prefix) accepts `driver`, `chunk_size`, `index_prefix`,
and driver-specific keys under `extra` — plus two fields (`soft_delete`,
`queue`) that are parsed but not currently wired to any behavior. See
[Configuration](configuration.md) for the full reference, including exactly
what does and doesn't work today.

## Indexing and searching

- [Indexing](indexing.md) — auto-sync on save/delete, batch import, pausing
  sync during bulk operations, conditionally searchable instances, soft
  delete.
- [Searching](searching.md) — where clauses (including the real Algolia/
  Meilisearch filter translation), custom indexes, pagination, raw results.

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
fiction-scout create-index myapp.models.Post         # create the index, if the driver supports it
fiction-scout delete-index myapp.models.Post         # delete the index entirely
```

Under Django, the same four subcommands are available as
`manage.py fiction_scout <subcommand> <dotted.model.Path>` — it calls the
identical underlying functions, just with Django's own argument parsing.

## Tutorials

Two full walkthroughs building the same Movies API — list, filter by
director/category, full-text search — end to end:

- [Django + Algolia](tutorials/django-algolia-movies-api.md)
- [FastAPI + SQLAlchemy](tutorials/fastapi-sqlalchemy-movies-api.md) (the
  built-in `database` driver — no external account needed)

See [Tutorials overview](tutorials/index.md) for how the two compare.

## Extending

- [Adding a search driver](extending/custom-drivers.md) — implement `Engine`,
  register it with `EngineManager.extend()`.
- [Adding an ORM adapter](extending/custom-adapters.md) — implement
  `SearchableAdapter` and `ScoutModel` for a new ORM.
