"""Shared write/search orchestration used by every ORM adapter and the CLI.

Both the Django and SQLAlchemy `SearchableMixin`s, and every standalone CLI
command, call these functions instead of reimplementing
sync/dispatch/pause-check logic per adapter — see the DRY points in
`CLAUDE.md`.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from fiction_scout.config import FictionScoutConfig
from fiction_scout.engines.manager import EngineManager
from fiction_scout.protocols import Dispatcher, SearchableAdapter
from fiction_scout.search.builder import Builder
from fiction_scout.sync.context import is_syncing_paused


def should_be_searchable(instance: Any, *, adapter: SearchableAdapter) -> bool:
    """Return whether `instance` is eligible to be indexed.

    Default: ineligible only when the model has soft-delete enabled and
    `instance` is currently soft-deleted. Mixins may layer an app-level
    override (an instance method of the same name) on top of this default.
    """
    model = type(instance)
    if adapter.soft_delete_enabled(model) and adapter.is_soft_deleted(instance):
        return False
    return True


def make_searchable(
    instances: Sequence[Any],
    *,
    adapter: SearchableAdapter,
    engine_manager: EngineManager,
    config: FictionScoutConfig,
    dispatcher: Dispatcher,
) -> None:
    """Index `instances`, dropping any `should_be_searchable` rejects."""
    if is_syncing_paused():
        return
    eligible = [i for i in instances if should_be_searchable(i, adapter=adapter)]
    if not eligible:
        return
    engine = engine_manager.driver()

    def _run() -> None:
        engine.update(eligible, adapter)

    dispatcher.dispatch(_run)


def make_unsearchable(
    instances: Sequence[Any],
    *,
    adapter: SearchableAdapter,
    engine_manager: EngineManager,
    config: FictionScoutConfig,
    dispatcher: Dispatcher,
) -> None:
    """Remove `instances` from the index."""
    if is_syncing_paused():
        return
    if not instances:
        return
    engine = engine_manager.driver()
    batch = list(instances)

    def _run() -> None:
        engine.delete(batch, adapter)

    dispatcher.dispatch(_run)


def make_all_searchable(
    model: type,
    *,
    adapter: SearchableAdapter,
    engine_manager: EngineManager,
    config: FictionScoutConfig,
    dispatcher: Dispatcher,
    chunk_size: int | None = None,
) -> None:
    """Index every record of `model`, `chunk_size` at a time.

    Each chunk is a separate `make_searchable` call (and so a separate
    dispatched write) rather than one call with every record — bounds
    memory use for large tables and lets a queue-backed dispatcher spread
    the work across multiple jobs.
    """
    if is_syncing_paused():
        return
    size = chunk_size if chunk_size is not None else config.chunk_size
    for chunk in adapter.chunk_records(model, chunk_size=size):
        make_searchable(
            chunk,
            adapter=adapter,
            engine_manager=engine_manager,
            config=config,
            dispatcher=dispatcher,
        )


def perform_search(
    model: type,
    term: str,
    *,
    adapter: SearchableAdapter,
    engine_manager: EngineManager,
    config: FictionScoutConfig,
    **kwargs: Any,
) -> Builder:
    """Build a `Builder` for `term` against `model`, bound to the resolved engine."""
    engine = engine_manager.driver()
    return Builder(model, term, engine=engine, adapter=adapter, **kwargs)
