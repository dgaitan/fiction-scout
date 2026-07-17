from __future__ import annotations

import asyncio

from fiction_scout.sync.context import is_syncing_paused, without_syncing_to_search


def test_syncing_is_not_paused_by_default() -> None:
    assert is_syncing_paused() is False


def test_without_syncing_to_search_pauses_for_the_block() -> None:
    assert is_syncing_paused() is False
    with without_syncing_to_search():
        assert is_syncing_paused() is True
    assert is_syncing_paused() is False


def test_nesting_restores_the_outer_state_on_exit() -> None:
    with without_syncing_to_search():
        assert is_syncing_paused() is True
        with without_syncing_to_search():
            assert is_syncing_paused() is True
        assert is_syncing_paused() is True
    assert is_syncing_paused() is False


def test_state_restored_even_if_the_block_raises() -> None:
    try:
        with without_syncing_to_search():
            raise ValueError("boom")
    except ValueError:
        pass
    assert is_syncing_paused() is False


def test_pause_propagates_into_asyncio_tasks() -> None:
    async def check_inside_task() -> bool:
        return is_syncing_paused()

    async def run() -> bool:
        with without_syncing_to_search():
            return await asyncio.create_task(check_inside_task())

    assert asyncio.run(run()) is True
