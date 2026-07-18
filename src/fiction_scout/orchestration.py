from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Literal

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


@dataclass(frozen=True)
class SyncJob:
    """One dispatched chunk of index-sync work.

    Not just a closure — `operation`/`model`/`batch` are exposed as plain
    fields so a queue-based `Dispatcher` (e.g. Celery, see
    `sync/dispatchers/celery.py`) can pull out picklable identifying data
    (a dotted model path, the batch's scout keys) instead of trying to
    serialize this object itself, which carries live `adapter`/
    `engine_manager` instances that may hold unpicklable resources (open
    network clients, ORM sessions). `SyncDispatcher` and any other
    in-process dispatcher don't need any of that — they just call the job
    like any other zero-arg callable, which runs against the exact live
    `batch` already in memory, no serialization involved.
    """

    operation: Literal["update", "delete"]
    model: type
    batch: list[Any]
    adapter: SearchableAdapter
    engine_manager: EngineManager

    def __call__(self) -> None:
        engine = self.engine_manager.driver()
        if self.operation == "update":
            engine.update(self.batch, self.adapter)
        else:
            engine.delete(self.batch, self.adapter)


def _dispatch_in_chunks(
    instances: list[Any],
    *,
    adapter: SearchableAdapter,
    engine_manager: EngineManager,
    dispatcher: Dispatcher,
    chunk_size: int | None,
    operation: Literal["update", "delete"],
) -> None:
    # One dispatch per chunk, not one dispatch for the whole list — a queue
    # dispatcher would otherwise have to serialize every instance into a
    # single task payload, and a real engine would get one unbounded batch.
    size = chunk_size if chunk_size is not None else engine_manager.config.chunk_size
    model = type(instances[0])
    for start in range(0, len(instances), size):
        batch = instances[start : start + size]
        dispatcher.dispatch(
            SyncJob(
                operation=operation,
                model=model,
                batch=batch,
                adapter=adapter,
                engine_manager=engine_manager,
            )
        )


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
    _dispatch_in_chunks(
        eligible,
        adapter=adapter,
        engine_manager=engine_manager,
        dispatcher=dispatcher,
        chunk_size=chunk_size,
        operation="update",
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
    _dispatch_in_chunks(
        list(instances),
        adapter=adapter,
        engine_manager=engine_manager,
        dispatcher=dispatcher,
        chunk_size=chunk_size,
        operation="delete",
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
