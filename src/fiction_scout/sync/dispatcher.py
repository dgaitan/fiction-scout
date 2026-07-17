"""The default, zero-configuration dispatcher: runs work immediately."""

from __future__ import annotations

from typing import Callable


class SyncDispatcher:
    """Runs indexing work immediately, in the calling thread.

    The default dispatcher and the fallback whenever no queue backend is
    configured — fiction-scout must work correctly with zero setup.
    Implements the `Dispatcher` protocol structurally (no inheritance
    required).
    """

    def dispatch(self, fn: Callable[[], None]) -> None:
        """Run `fn` immediately."""
        fn()
