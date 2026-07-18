"""Proves `MeilisearchEngine` works against a real Meilisearch server.

`test_meilisearch_engine.py` already proves this engine's own logic is
correct against `FakeMeilisearchClient`. What that suite can't prove is that
the real `meilisearch` client's response shapes (`hits`,
`estimatedTotalHits`, the `index_not_found` error code) actually match what
`MeilisearchEngine` assumes — these tests exercise the real wire boundary
instead. Skipped (not failed) when no server is reachable; see
`conftest.py` for the `live_client` fixture's fallback chain.
"""

from __future__ import annotations

import time
import uuid
from typing import Any

import meilisearch
import pytest

from fiction_scout.engines.meilisearch import MeilisearchEngine
from fiction_scout.search.builder import Builder
from tests.support import Article, FakeAdapter

pytestmark = [pytest.mark.meilisearch]


class _UniqueIndexAdapter(FakeAdapter):
    """A `FakeAdapter` whose index name is unique per test.

    Every live test shares one long-lived server (whether launched by the
    fixture or pointed at via `MEILISEARCH_TEST_URL`), so tests need their
    own index to avoid seeing each other's documents.
    """

    def __init__(self, records: list[Any], *, index_name: str) -> None:
        super().__init__(records)
        self._index_name = index_name

    def searchable_as(self, model: type) -> str:
        return self._index_name


def _poll_until(predicate: Any, *, timeout: float = 5.0, interval: float = 0.1) -> Any:
    deadline = time.monotonic() + timeout
    result = predicate()
    while not result and time.monotonic() < deadline:
        time.sleep(interval)
        result = predicate()
    return result


@pytest.fixture
def index_name() -> str:
    return f"fiction-scout-test-{uuid.uuid4().hex}"


@pytest.fixture(autouse=True)
def _cleanup_index(live_client: meilisearch.Client, index_name: str) -> Any:
    yield
    try:
        task = live_client.delete_index(index_name)
        live_client.wait_for_task(task.task_uid)
    except meilisearch.errors.MeilisearchApiError:
        pass


def test_given_instances_when_update_called_then_documents_become_searchable(
    live_client: meilisearch.Client, index_name: str
) -> None:
    articles = [
        Article(id=1, title="Star Wars", body="A New Hope"),
        Article(id=2, title="Star Trek", body="The Wrath of Khan"),
    ]
    adapter = _UniqueIndexAdapter(articles, index_name=index_name)
    engine = MeilisearchEngine(client=live_client)

    engine.update(articles, adapter)

    # "New Hope" only appears in the first article's body — Meilisearch's
    # default relevance ranking would also surface the second article for a
    # broader query like "star wars" (it shares the word "star"), which
    # isn't what this test is proving.
    builder = Builder(Article, "New Hope", engine=engine, adapter=adapter)
    results = _poll_until(lambda: builder.get())

    assert results == [articles[0]]


def test_given_instances_when_delete_called_then_removed_from_index(
    live_client: meilisearch.Client, index_name: str
) -> None:
    articles = [Article(id=1, title="Star Wars", body="A New Hope")]
    adapter = _UniqueIndexAdapter(articles, index_name=index_name)
    engine = MeilisearchEngine(client=live_client)
    engine.update(articles, adapter)
    builder = Builder(Article, "star wars", engine=engine, adapter=adapter)
    _poll_until(lambda: builder.get())

    engine.delete(articles, adapter)

    assert _poll_until(lambda: builder.get() == [], timeout=5.0) is True


def test_given_flush_called_then_index_emptied_but_settings_survive(
    live_client: meilisearch.Client, index_name: str
) -> None:
    articles = [Article(id=1, title="Star Wars", body="A New Hope")]
    adapter = _UniqueIndexAdapter(articles, index_name=index_name)
    engine = MeilisearchEngine(client=live_client)
    engine.create_index(index_name, primary_key="id")
    engine.update(articles, adapter)
    builder = Builder(Article, "star wars", engine=engine, adapter=adapter)
    _poll_until(lambda: builder.get())

    engine.flush(Article, adapter)

    assert _poll_until(lambda: builder.get() == [], timeout=5.0) is True
    assert live_client.get_index(index_name).primary_key == "id"


def test_given_index_missing_when_create_index_called_twice_then_second_call_is_noop(
    live_client: meilisearch.Client, index_name: str
) -> None:
    engine = MeilisearchEngine(client=live_client)

    engine.create_index(index_name, primary_key="id")
    engine.create_index(index_name, primary_key="id")

    assert live_client.get_index(index_name).primary_key == "id"


def test_given_delete_index_called_then_index_no_longer_exists(
    live_client: meilisearch.Client, index_name: str
) -> None:
    engine = MeilisearchEngine(client=live_client)
    engine.create_index(index_name, primary_key="id")

    engine.delete_index(index_name)

    with pytest.raises(meilisearch.errors.MeilisearchApiError) as excinfo:
        live_client.get_index(index_name)
    assert excinfo.value.code == "index_not_found"
