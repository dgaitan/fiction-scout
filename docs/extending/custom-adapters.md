# Adding an ORM adapter

An adapter translates between one ORM's models and fiction-scout's core.
Engines, the search `Builder`, and the CLI never import Django or SQLAlchemy
directly — everything talks to the `SearchableAdapter` protocol in
`fiction_scout.protocols`. That's the seam that makes a new ORM a
pure-addition change: the Django adapter is the only shipped, tested
reference to build a second one against, since the SQLAlchemy adapter
hasn't landed yet.

A full adapter has three pieces, mirroring `adapters/django/`:

1. **A `SearchableAdapter` implementation** — the ORM-facing half, called by
   engines and the CLI.
2. **A `SearchableMixin`** — the model-facing half, giving your ORM's models
   `.search()`, `.searchable()`, `.unsearchable()`, etc.
3. **A sync trigger** — whatever your ORM's change-tracking mechanism is
   (Django signals, SQLAlchemy session events, …), wired to call
   `orchestration.make_searchable`/`make_unsearchable` when a row changes.

## 1. `SearchableAdapter`

A structural `Protocol` (`typing.Protocol`, `@runtime_checkable`) — no base
class to inherit from, just implement every method. Two groups:

**Per-instance/per-model methods**, delegated to the model itself in the
Django adapter (see below for why):

```python
def searchable_as(self, model: type) -> str: ...
def get_scout_key(self, instance) -> Any: ...
def get_scout_key_name(self, model: type) -> str: ...
def to_searchable_array(self, instance) -> dict[str, Any]: ...
def chunk_records(self, model: type, *, chunk_size: int) -> Iterator[list]: ...
def fetch_by_ids(self, model: type, ids: Sequence) -> list: ...
def is_soft_deleted(self, instance) -> bool: ...
def soft_delete_enabled(self, model: type) -> bool: ...
```

**Query-building methods**, used only by the `database` engine (the
`collection`/`algolia`/`meilisearch` engines never call these — they read
records directly or fetch by id):

```python
def query_all(self, model: type) -> Any: ...
def apply_search_term(self, query, model: type, term: str) -> Any: ...
def apply_where(self, query, field: str, value: Any) -> Any: ...
def apply_where_in(self, query, field: str, values: Sequence) -> Any: ...
def apply_where_not_in(self, query, field: str, values: Sequence) -> Any: ...
def apply_trashed_filter(self, query, model: type, *, with_trashed: bool, only_trashed: bool) -> Any: ...
def execute_query(self, query) -> list: ...
def count_query(self, query) -> int: ...
def paginate_query(self, query, *, per_page: int, page: int) -> list: ...
```

`query` is an opaque, adapter-specific object (a Django `QuerySet`, a
SQLAlchemy `Select`) — the `database` engine threads it through these calls
without ever inspecting it.

**Delegate model-specific logic to the mixin, don't reimplement it in the
adapter.** `DjangoAdapter.searchable_as(model)` is a one-line call to
`model.searchable_as()`; the mixin owns the actual logic
(`cls._meta.db_table`). The adapter's job is translating the
`SearchableAdapter` protocol's shape into ORM-specific calls, not owning
per-model behavior — that's what keeps `to_searchable_array` overridable per
model without touching the adapter.

## 2. `SearchableMixin`

Every adapter's mixin must expose the **same public method surface** — this
is enforced by CLAUDE.md's DRY note and is the actual contract app code
depends on:

```python
to_searchable_array() -> dict[str, Any]
searchable_as() -> str          # classmethod
get_scout_key() -> Any
get_scout_key_name() -> str     # classmethod
search(term="", **kwargs) -> Builder   # classmethod
searchable() -> None
unsearchable() -> None
should_be_searchable() -> bool
```

Plus the three `ScoutModel` protocol classmethods the CLI resolves a dotted
model path through:

```python
get_scout_adapter() -> SearchableAdapter        # classmethod
get_scout_engine_manager() -> EngineManager      # classmethod
get_scout_dispatcher() -> Dispatcher             # classmethod
```

`fiction_scout.adapters.django.mixin.SearchableMixin` implements all of the
above by delegating to `fiction_scout.orchestration` for the actual
sync/dispatch/search logic and to a small `runtime.py` module for its
adapter/engine-manager/dispatcher singletons:

```python
def searchable(self) -> None:
    orchestration.make_searchable(
        [self],
        adapter=runtime.get_adapter(),
        engine_manager=runtime.get_engine_manager(),
        dispatcher=runtime.get_dispatcher(),
    )
```

**Never reimplement `orchestration`'s logic in a mixin.** It already handles
pause-checking (`sync.context.is_syncing_paused()`), chunking, and routing
through the `Dispatcher` protocol — a new ORM's mixin should be a thin
delegation layer, the same shape as the Django one.

### The `runtime.py` pattern

A per-ORM module holding lazy module-level singletons:

```python
_adapter: DjangoAdapter | None = None
_engine_manager: EngineManager | None = None
_dispatcher: SyncDispatcher | None = None


def get_adapter() -> DjangoAdapter:
    global _adapter
    if _adapter is None:
        _adapter = DjangoAdapter()
    return _adapter
```

Plain globals, not `functools.lru_cache` — that's deliberate, not an
oversight. Tests need to swap these out directly
(`monkeypatch.setattr(runtime, "_engine_manager", ...)`) to point a real
mixin at a `SpyEngine`-backed manager without fighting cache invalidation,
and a real singleton matters in production too: it's the only way an app's
own `EngineManager.extend()` custom-driver registration survives across
requests.

## 3. Wiring the sync trigger

This is the one piece that's genuinely ORM-specific, and the one place
CLAUDE.md explicitly forbids collapsing two adapters' mechanisms into "the
same thing":

- **Django** connects `post_save`/`post_delete` signals globally in
  `AppConfig.ready()`, filtered with
  `isinstance(instance, SearchableMixin)` (Django signals have no built-in
  "only my mixin's subclasses" filter). Neither handler checks
  `is_syncing_paused()` itself — `orchestration.make_searchable`/
  `make_unsearchable` already do, and duplicating the check in the signal
  handler would violate the DRY principle this whole design exists to
  enforce.
- **A future SQLAlchemy adapter** would need a session `after_commit` hook,
  *not* `after_insert` — SQLAlchemy must avoid indexing rows from a
  transaction that later rolls back, a failure mode Django's
  post-commit-adjacent signals don't share in the same way. When this
  adapter is built, that reasoning belongs in the module docstring of the
  file implementing the hook, not just in this doc.

Don't assume every ORM's sync trigger looks like Django's — re-derive from
your ORM's actual commit/rollback semantics before choosing where to hook
in.

## Registering config resolution

If your ORM has its own settings mechanism (like Django's `settings.py` /
`FICTION_SCOUT` dict), add a resolver to `fiction_scout.config._RESOLVERS` —
see `_resolve_django`/`_resolve_flask` for the pattern. If it doesn't,
environment-variable and explicit-construction resolution already work with
zero adapter-specific code.

## Real implementation to read

`src/fiction_scout/adapters/django/` — `adapter.py` (the
`SearchableAdapter` implementation), `mixin.py` (the model-facing surface),
`runtime.py` (the singleton pattern), `signals.py` +`apps.py` (the sync
trigger). Read it end to end before starting a second adapter; the shape
should look almost identical for anything with real transactional
semantics.
