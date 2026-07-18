# Adding a search driver

A driver is a subclass of `fiction_scout.engines.base.Engine`, registered
with an `EngineManager`. Core code (`search/builder.py`, `orchestration.py`,
the CLI) never imports a specific driver's SDK directly — it only calls
`Engine`'s abstract methods. This is the same seam the built-in `algolia`
and `meilisearch` drivers use, so a third-party driver is a pure-addition
change, never a core-code change.

## The `Engine` contract

```python
from fiction_scout.engines.base import Engine, Page


class MyEngine(Engine):
    def update(self, models: list, adapter) -> None:
        """Add or update `models` in the index."""

    def delete(self, models: list, adapter) -> None:
        """Remove `models` from the index."""

    def flush(self, model: type, adapter) -> None:
        """Remove every record of `model` from the index."""

    def search(self, builder) -> object:
        """Execute `builder` and return raw, engine-specific results."""

    def paginate(self, builder, per_page: int, page: int) -> Page:
        """Execute `builder` and return one page of matching model instances."""

    def map_ids(self, results) -> list:
        """Extract the ordered list of scout keys from raw `results`."""

    def map(self, builder, results, model: type) -> list:
        """Convert raw `results` into a list of `model` instances."""

    def get_total_count(self, results) -> int:
        """Extract the total match count from raw `results`."""
```

Four more methods have default implementations you can override:

- `index_name_for(model, adapter)` — defaults to
  `adapter.searchable_as(model)`. Override this (not `searchable_as` itself,
  which `database`/`collection` also rely on for their real table name) if
  your driver is backed by a separate external index and should honor
  `FictionScoutConfig.index_prefix` — see `AlgoliaEngine`/`MeilisearchEngine`
  for the pattern, and [Configuration: multi-tenancy](../configuration.md#multi-tenancy-with-index_prefix).
- `create_index(name, **options)` — no-ops by default.
- `delete_index(name)` — no-ops by default.
- `update_index_settings(model, adapter, **settings)` — **raises**
  `IndexSettingsNotSupportedError` by default, since the CLI's
  `sync-index-settings` command relies on that raise to report "this driver
  doesn't support settings" rather than silently doing nothing. Only
  override this if your driver has a real settings API (both Algolia and
  Meilisearch do — see their "Index settings" docs for the whitelist pattern
  worth reusing).

`Engine` also supplies two concrete convenience methods built on the
abstract ones above — you don't implement these yourself:

- `keys(builder)` → `self.map_ids(self.search(builder))`
- `get(builder)` → `self.map(builder, self.search(builder), builder.model)`

## Mapping external-index results back to model instances

An engine backed by an external index (Algolia, Meilisearch, a future
Elasticsearch driver) doesn't get live model rows back from a search — it
gets index documents. The pattern every such driver follows: `map()` = `map_ids()`
(extract scout keys from the raw response) + `adapter.fetch_by_ids(model, ids)`
(look the real rows up). A shared helper already does this:

```python
from fiction_scout.engines._external_index import fetch_matched_models


class MyEngine(Engine):
    def map(self, builder, results, model):
        ids = self.map_ids(results)
        return fetch_matched_models(builder.adapter, model, ids)
```

`fetch_matched_models` compares ids via `str()` on both sides — reuse it
rather than re-deriving the same four lines; it already handles the case
where the index's key type (e.g. Algolia's always-string `objectID`) doesn't
match the model's own primary-key type.

The `database` and `collection` engines don't need this helper: they read
live rows directly, they're never backed by a separate index.

## A minimal worked example

```python
from fiction_scout.engines.base import Engine, Page
from fiction_scout.engines._external_index import fetch_matched_models


class InMemoryDictEngine(Engine):
    """Toy driver: a process-global dict keyed by index name."""

    def __init__(self) -> None:
        self._indexes: dict[str, dict] = {}

    def update(self, models, adapter) -> None:
        for instance in models:
            array = adapter.to_searchable_array(instance)
            if not array:
                continue
            index = self._indexes.setdefault(adapter.searchable_as(type(instance)), {})
            index[adapter.get_scout_key(instance)] = array

    def delete(self, models, adapter) -> None:
        for instance in models:
            index = self._indexes.get(adapter.searchable_as(type(instance)), {})
            index.pop(adapter.get_scout_key(instance), None)

    def flush(self, model, adapter) -> None:
        self._indexes.pop(adapter.searchable_as(model), None)

    def search(self, builder):
        index = self._indexes.get(builder.adapter.searchable_as(builder.model), {})
        term = builder.term.lower()
        return [
            key
            for key, array in index.items()
            if any(term in str(value).lower() for value in array.values())
        ]

    def paginate(self, builder, per_page, page):
        ids = self.search(builder)
        start = (page - 1) * per_page
        items = fetch_matched_models(
            builder.adapter, builder.model, ids[start : start + per_page]
        )
        return Page(items, total=len(ids), page=page, per_page=per_page)

    def map_ids(self, results):
        return results

    def map(self, builder, results, model):
        return fetch_matched_models(builder.adapter, model, results)

    def get_total_count(self, results):
        return len(results)
```

## Registering it

Nothing in `EngineManager` needs to change — `.extend()` is the entire
registration API:

```python
from fiction_scout.engines.manager import EngineManager

manager = EngineManager()
manager.extend("in_memory_dict", InMemoryDictEngine)
```

Set `FICTION_SCOUT = {"driver": "in_memory_dict"}` (or configure the
resolved `EngineManager` used by your adapter's `runtime` module) to select
it as the default.

If your driver depends on an optional third-party SDK, validate it the same
way the built-in `algolia`/`meilisearch` drivers do — call
`fiction_scout.dependencies.require_installed(feature, module_name, extra)`
before importing the SDK, so a missing package surfaces as a clear
`MissingDependencyError` naming the pip extra to install, not a raw
`ImportError` from inside your engine.

## Real implementations to read

`src/fiction_scout/engines/algolia.py` and
`src/fiction_scout/engines/meilisearch.py` are complete, tested drivers —
each module's docstring records the design decisions specific to that
backend (test strategy, index-creation semantics, soft-delete handling,
`where()`-filter translation, index-settings whitelisting). Read one of
those before starting a new driver; the shape is almost always the same.
