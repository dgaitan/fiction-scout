"""Pause automatic index syncing for a block of code."""

from __future__ import annotations

import contextlib
from collections.abc import Iterator
from contextvars import ContextVar

_syncing_paused: ContextVar[bool] = ContextVar(
    "fiction_scout_syncing_paused", default=False
)


def is_syncing_paused() -> bool:
    """Return whether automatic index syncing is currently paused."""
    return _syncing_paused.get()


@contextlib.contextmanager
def without_syncing_to_search() -> Iterator[None]:
    """Pause automatic index syncing for the duration of this block.

    Built on `contextvars.ContextVar` rather than `threading.local` so the
    pause propagates correctly into `asyncio` tasks spawned inside the
    block — a deliberate choice made now so a future async adapter (see
    ROADMAP.md) doesn't require redesigning this primitive.

    Nests safely: the innermost block's exit restores exactly the state that
    was active before it, not a hardcoded "unpaused".
    """
    token = _syncing_paused.set(True)
    try:
        yield
    finally:
        _syncing_paused.reset(token)
