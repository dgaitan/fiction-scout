"""Sync a SQLAlchemy session's committed changes to the configured engine.

Hooked on `Session`'s `before_commit`/`after_commit` events, not the
per-row `after_insert`/`after_update`/`after_delete` mapper events. Those
fire *during* `session.flush()`, before the surrounding transaction is
guaranteed to actually land — a transaction that flushes cleanly can still
roll back afterward (an outer `with session.begin():` block re-raising, a
later statement in the same transaction failing), and indexing on
`after_insert` would push rows into the search engine that never actually
exist in the database once that rollback completes.

The two-hook split exists because `session.new`/`dirty`/`deleted` are only
reliably populated *before* the flush that a commit triggers:
`before_commit` fires first (verified against SQLAlchemy's
`SessionTransaction._prepare_impl()`, which dispatches `before_commit`
before running the flush), so it's used only to *capture* which instances
are about to be committed — captured by object identity, not serialized,
since flush (which runs between the two hooks) is what populates
autoincrement primary keys on those same Python objects. `after_commit`
fires after flush *and* after the real database commit, but before
`Session.commit()`'s own post-commit `expire_all()` — so the actual engine
calls happen there, once the transaction is provably durable, using
instances whose attributes (including freshly-assigned PKs) are still
safely readable with no extra queries. A rolled-back transaction never
fires `after_commit` at all, so nothing captured at `before_commit` is ever
sent — this is the concrete mechanism the Gherkin scenario for rollback
safety proves, no extra guard code required.
"""

from __future__ import annotations

from typing import Any
from weakref import WeakKeyDictionary

from sqlalchemy import event
from sqlalchemy.orm import Session

from fiction_scout import orchestration
from fiction_scout.adapters.sqlalchemy import runtime
from fiction_scout.adapters.sqlalchemy.mixin import SearchableMixin

_Pending = tuple[list[Any], list[Any]]
_pending: WeakKeyDictionary[Session, _Pending] = WeakKeyDictionary()


def _capture_pending(session: Session) -> None:
    to_sync = [
        obj
        for obj in {*session.new, *session.dirty}
        if isinstance(obj, SearchableMixin)
    ]
    hard_deleted = [obj for obj in session.deleted if isinstance(obj, SearchableMixin)]
    if to_sync or hard_deleted:
        _pending[session] = (to_sync, hard_deleted)


def _flush_pending(session: Session) -> None:
    to_sync, hard_deleted = _pending.pop(session, ([], []))
    if not to_sync and not hard_deleted:
        return
    adapter = runtime.get_adapter()
    engine_manager = runtime.get_engine_manager()
    dispatcher = runtime.get_dispatcher()
    searchable = [instance for instance in to_sync if instance.should_be_searchable()]
    unsearchable = [
        instance for instance in to_sync if not instance.should_be_searchable()
    ]
    if searchable:
        orchestration.make_searchable(
            searchable,
            adapter=adapter,
            engine_manager=engine_manager,
            dispatcher=dispatcher,
        )
    to_remove = unsearchable + hard_deleted
    if to_remove:
        orchestration.make_unsearchable(
            to_remove,
            adapter=adapter,
            engine_manager=engine_manager,
            dispatcher=dispatcher,
        )


def connect_events() -> None:
    if not event.contains(Session, "before_commit", _capture_pending):
        event.listen(Session, "before_commit", _capture_pending)
    if not event.contains(Session, "after_commit", _flush_pending):
        event.listen(Session, "after_commit", _flush_pending)
