"""Celery-backed `Dispatcher`: hands index-sync work to a background worker.

**Design decision (recorded before writing tests against this module, per
the same bar `adapters/sqlalchemy/events.py` sets for its `after_commit`
choice):**

`orchestration._dispatch_in_chunks` hands each chunk to `dispatcher.dispatch()`
as a `SyncJob` — a dataclass, not a bare closure, but one that still carries
live `adapter`/`engine_manager` instances (and, via `SyncJob.batch`, live
model instances). `SyncDispatcher` just calls it directly: no serialization,
so none of that matters. A Celery broker is a different story — closures
aren't picklable at all, and shipping the live `adapter`/`engine_manager`
themselves is fragile even where technically possible, since a real engine
may hold an open network client that was never meant to cross a process
boundary.

Two options were on the table: (a) dispatch picklable *data* — a model's
dotted import path plus its batch's scout keys plus an operation name — to
one named Celery task that reconstructs and runs the operation on the
worker; or (b) narrow the dispatcher so it only ever accepts the specific
operations it can actually support, rather than any arbitrary closure.

**Chosen: both, deliberately combined.** (a) is the actual dispatch
mechanism: `CeleryDispatcher.dispatch()` pulls `model`/`batch`/`operation`
off the `SyncJob` it's given, converts the batch to scout keys via
`adapter.get_scout_key()` *while the instances are still live* (this
happens in the calling process, before anything crosses the broker), and
sends `(model_dotted_path, ids, operation)` — three plain, JSON-picklable
values — to one shared task, `_run_sync_job`. That task resolves the model
via `cli.model_resolution.resolve_model` (the standalone CLI's exact
mechanism, reused rather than reinvented) and gets a *fresh* adapter/engine_manager
via the model's own `ScoutModel.get_scout_adapter()` /
`get_scout_engine_manager()` classmethods — never the caller's pickled
instances, which is what keeps this safe regardless of what those objects
hold.

(b) shows up as an explicit boundary, not the whole design:
`CeleryDispatcher.dispatch()` only accepts a `SyncJob` — the one shape
`orchestration.py` actually produces — and raises `TypeError` for anything
else, rather than silently mishandling an arbitrary closure it has no way
to serialize.

**Known limitation, not silently papered over:** re-fetching by id on the
worker (`adapter.fetch_by_ids(model, ids)`) is correct for `update` — the
row must currently exist for a sync to make sense, and re-fetching (instead
of shipping stale in-memory field values) means the worker indexes whatever
the row actually looks like by the time the job runs, which is the right
behavior for a queue where the job might sit for a while. It is *not*
reliable for `delete`: a hard delete (Django's `post_delete` signal) means
the row is already gone from the database by dispatch time, so
`fetch_by_ids` finds nothing on the worker and the index entry is never
removed. A soft-delete-driven `make_unsearchable` call (the row still
exists, just flagged) works correctly. Making hard-delete dispatch fully
correct would mean `Engine.delete()` accepting scout keys directly instead
of model instances — a change to the shared `Engine` contract every driver
(current and future) implements, which is out of scope for this dispatcher.
This module's own test coverage is scoped to the `update`/sync path for
exactly this reason.
"""

from __future__ import annotations

from typing import Any, Callable

from fiction_scout.cli.model_resolution import model_dotted_path, resolve_model
from fiction_scout.dependencies import require_installed
from fiction_scout.orchestration import SyncJob

_task: Any = None


def _run_sync_job(model_path: str, ids: list[Any], operation: str) -> None:
    model = resolve_model(model_path)
    adapter = model.get_scout_adapter()
    engine = model.get_scout_engine_manager().driver()
    instances = adapter.fetch_by_ids(model, ids)
    if operation == "update":
        engine.update(instances, adapter)
    else:
        engine.delete(instances, adapter)


def _get_task() -> Any:
    global _task
    if _task is None:
        from celery import shared_task

        _task = shared_task(name="fiction_scout.sync_job")(_run_sync_job)
    return _task


class CeleryDispatcher:
    """Dispatches index-sync work to Celery via one shared task.

    Implements the `Dispatcher` protocol structurally, but only for
    `SyncJob`s — see the module docstring for why an arbitrary
    `Callable[[], None]` can't be supported the way `SyncDispatcher`
    supports one.
    """

    def __init__(self) -> None:
        require_installed(
            feature="Celery dispatcher", module_name="celery", extra="celery"
        )

    def dispatch(self, fn: Callable[[], None]) -> None:
        if not isinstance(fn, SyncJob):
            raise TypeError(
                "CeleryDispatcher only dispatches SyncJob instances produced by "
                "fiction_scout.orchestration, not arbitrary callables."
            )
        ids = [fn.adapter.get_scout_key(instance) for instance in fn.batch]
        _get_task().delay(model_dotted_path(fn.model), ids, fn.operation)
