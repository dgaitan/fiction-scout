from __future__ import annotations

from fiction_scout.sync.dispatcher import SyncDispatcher


def test_dispatch_runs_the_function_immediately() -> None:
    calls = []
    dispatcher = SyncDispatcher()

    dispatcher.dispatch(lambda: calls.append(1))

    assert calls == [1]
