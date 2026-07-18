from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Callable

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


def _dispatch_in_chunks(
    instances: list[Any],
    *,
    engine_manager: EngineManager,
    dispatcher: Dispatcher,
    chunk_size: int | None,
    action: Callable[[list[Any]], None],
) -> None:
    # One dispatch per chunk, not one dispatch for the whole list — a queue
    # dispatcher would otherwise have to serialize every instance into a
    # single task payload, and a real engine would get one unbounded batch.
    size = chunk_size if chunk_size is not None else engine_manager.config.chunk_size
    for start in range(0, len(instances), size):
        batch = instances[start : start + size]

        def _run(batch: list[Any] = batch) -> None:
            action(batch)

        dispatcher.dispatch(_run)


def make_searchable(
    instances: Sequence[Any],
    *,
    adapter: SearchableAdapter,
    engine_manager: EngineManager,
    dispatcher: Dispatcher,
    chunk_size: int | None = None,
) -> None:
    if is_syncing_paused():
        return
    eligible = [i for i in instances if should_be_searchable(i, adapter=adapter)]
    if not eligible:
        return
    engine = engine_manager.driver()
    _dispatch_in_chunks(
        eligible,
        engine_manager=engine_manager,
        dispatcher=dispatcher,
        chunk_size=chunk_size,
        action=lambda batch: engine.update(batch, adapter),
    )


def make_unsearchable(
    instances: Sequence[Any],
    *,
    adapter: SearchableAdapter,
    engine_manager: EngineManager,
    dispatcher: Dispatcher,
    chunk_size: int | None = None,
) -> None:
    if is_syncing_paused():
        return
    if not instances:
        return
    engine = engine_manager.driver()
    _dispatch_in_chunks(
        list(instances),
        engine_manager=engine_manager,
        dispatcher=dispatcher,
        chunk_size=chunk_size,
        action=lambda batch: engine.delete(batch, adapter),
    )


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
            chunk_size=size,
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
