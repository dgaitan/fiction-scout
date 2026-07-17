# Roadmap

## Shipped in v1

- Framework-agnostic core: `Engine` contract, `EngineManager`, search `Builder`,
  `FictionScoutConfig` resolution chain, `withoutSyncingToSearch` context manager.
- `DatabaseEngine` (`LIKE` queries by default, opt-in full-text/prefix column
  strategies) and `CollectionEngine` (in-memory, zero dependencies).
- Django ORM adapter (signal-based auto-sync) and SQLAlchemy adapter
  (session-`after_commit`-based auto-sync).
- Standalone CLI (`fiction-scout import|queue-import|flush|sync-index-settings`)
  and a Django management command bridge (`manage.py fiction_scout ...`) that
  wraps the same underlying functions.
- Pluggable `Dispatcher` protocol for background execution, with a synchronous
  default and a Celery reference adapter.
- Declared-field soft-delete convention (`soft_delete_field` on the mixin).

## Deliberately deferred (not v1)

These are out of scope for v1 by explicit decision, not oversight — each has a
concrete extension point already built for it:

- **Third-party search engines** — Algolia, Meilisearch, Typesense. The
  `Engine` ABC and `EngineManager.extend()` are the exact seam a future driver
  plugs into; see `docs/extending/custom-drivers.md` for a worked example.
  Dependency-validation (checking the SDK is installed, telling the user which
  extra to `pip install`) is already implemented in `EngineManager` and
  exercised today by the Celery dispatcher — a new driver reuses the same
  mechanism, it isn't new machinery.
- **Async support** — async Django ORM methods, SQLAlchemy's asyncio engine,
  async views. Sync-only for v1. `withoutSyncingToSearch` is deliberately
  built on `contextvars.ContextVar` rather than `threading.local` specifically
  so it propagates correctly into asyncio tasks once an async adapter exists —
  that choice was made now to avoid a breaking redesign later.
- **Additional ORM adapters** — Peewee, Tortoise ORM, plain dataclasses/attrs
  models via the raw `SearchableAdapter` protocol. The protocol is
  ORM-agnostic already; `docs/extending/custom-adapters.md` works through
  adding one.
- **Additional queue backends** — RQ, Django-Q, Huey. The `Dispatcher`
  protocol is the seam; Celery is the only reference implementation shipped.
