from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from fiction_scout.engines.manager import EngineManager
from fiction_scout.protocols import Dispatcher, SearchableAdapter
from fiction_scout.search.builder import Builder
from fiction_scout.sync.context import is_syncing_paused


def should_be_searchable(instance: Any, *, adapter: SearchableAdapter) -> bool:
    """Ineligible only if soft-deleted; mixins may override per model."""
    model = type(instance)
    if adapter.soft_delete_enabled(model) and adapter.is_soft_deleted(instance):
        return False
    return True


def make_searchable(
    instances: Sequence[Any],
    *,
    adapter: SearchableAdapter,
    engine_manager: EngineManager,
    dispatcher: Dispatcher,
) -> None:
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
    dispatcher: Dispatcher,
) -> None:
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
    dispatcher: Dispatcher,
    chunk_size: int | None = None,
) -> None:
    # One make_searchable call per chunk, not one call with every record —
    # bounds memory for large tables and lets a queue dispatcher spread the
    # work across multiple jobs.
    if is_syncing_paused():
        return
    size = chunk_size if chunk_size is not None else engine_manager.config.chunk_size
    for chunk in adapter.chunk_records(model, chunk_size=size):
        make_searchable(
            chunk,
            adapter=adapter,
            engine_manager=engine_manager,
            dispatcher=dispatcher,
        )


def perform_search(
    model: type,
    term: str,
    *,
    adapter: SearchableAdapter,
    engine_manager: EngineManager,
    **kwargs: Any,
) -> Builder:
    engine = engine_manager.driver()
    return Builder(model, term, engine=engine, adapter=adapter, **kwargs)
