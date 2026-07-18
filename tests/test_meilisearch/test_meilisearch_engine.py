from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from fiction_scout import orchestration
from fiction_scout.config import FictionScoutConfig
from fiction_scout.engines.manager import EngineManager
from fiction_scout.engines.meilisearch import MeilisearchEngine
from fiction_scout.exceptions import MissingDependencyError
from fiction_scout.search.builder import Builder
from tests.support import Article, FakeAdapter, FakeMeilisearchClient, SpyDispatcher

pytestmark = [pytest.mark.meilisearch]


@dataclass
class _BlankArticle:
    """A model whose `to_searchable_array()` is empty."""

    id: int

    def to_searchable_array(self) -> dict[str, Any]:
        return {}


def test_given_instances_when_update_called_then_add_documents_carries_primary_key(
    articles: list[Article], adapter: FakeAdapter
) -> None:
    client = FakeMeilisearchClient()
    engine = MeilisearchEngine(client=client)

    engine.update([articles[0], articles[1]], adapter)

    assert len(client.added) == 1
    index_name, documents, primary_key = client.added[0]
    assert index_name == "articles"
    assert primary_key == "id"
    assert documents == [
        {"id": 1, "title": "Star Trek II", "body": "The Wrath of Khan"},
        {"id": 2, "title": "Star Wars", "body": "A New Hope"},
    ]


def test_given_empty_searchable_array_when_update_called_then_excluded() -> None:
    blank = _BlankArticle(id=99)
    keepable = Article(id=1, title="Star Trek II", body="The Wrath of Khan")
    fake_adapter = FakeAdapter([blank, keepable])
    client = FakeMeilisearchClient()
    engine = MeilisearchEngine(client=client)

    engine.update([blank, keepable], fake_adapter)

    assert len(client.added) == 1
    _, documents, _ = client.added[0]
    assert [document["id"] for document in documents] == [1]


def test_given_instances_when_delete_called_then_delete_documents_carries_scout_keys(
    articles: list[Article], adapter: FakeAdapter
) -> None:
    client = FakeMeilisearchClient()
    engine = MeilisearchEngine(client=client)

    engine.delete([articles[0], articles[1]], adapter)

    assert client.deleted == [("articles", [1, 2])]


def test_given_flush_called_then_delete_all_documents_empties_only_that_models_index(
    adapter: FakeAdapter,
) -> None:
    client = FakeMeilisearchClient()
    engine = MeilisearchEngine(client=client)

    engine.flush(Article, adapter)

    assert client.cleared == ["articles"]


def test_given_search_term_when_get_called_then_returns_model_instances(
    articles: list[Article], adapter: FakeAdapter
) -> None:
    client = FakeMeilisearchClient(
        search_hits=[
            {"id": 1, "title": "Star Trek II"},
            {"id": 2, "title": "Star Wars"},
        ],
        estimated_total_hits=2,
    )
    engine = MeilisearchEngine(client=client)
    builder = Builder(Article, "star", engine=engine, adapter=adapter)

    results = builder.get()

    assert results == [articles[0], articles[1]]
    index_name, query, params = client.search_calls[0]
    assert index_name == "articles"
    assert query == "star"
    assert params["offset"] == 0


def test_given_index_does_not_exist_when_search_called_then_empty_results_not_raised(
    adapter: FakeAdapter,
) -> None:
    # Meilisearch only creates an index implicitly on first write, so a
    # model with nothing synced yet has no index at all — searching it must
    # behave like an existing-but-empty index, not raise `index_not_found`.
    client = FakeMeilisearchClient(search_raises_index_not_found=True)
    engine = MeilisearchEngine(client=client)
    builder = Builder(Article, "star", engine=engine, adapter=adapter)

    results = builder.get()

    assert results == []


def test_given_missing_index_when_create_index_called_then_created_with_pk() -> None:
    client = FakeMeilisearchClient()
    engine = MeilisearchEngine(client=client)

    engine.create_index("articles", primary_key="id")

    assert client.created == [("articles", {"primaryKey": "id"})]
    assert client.waited_task_uids == [0]


def test_given_index_already_exists_when_create_index_called_then_not_recreated() -> (
    None
):
    client = FakeMeilisearchClient(existing_index_uids={"articles"})
    engine = MeilisearchEngine(client=client)

    engine.create_index("articles", primary_key="id")

    assert client.created == []


def test_given_delete_index_called_then_client_delete_index_invoked() -> None:
    client = FakeMeilisearchClient()
    engine = MeilisearchEngine(client=client)

    engine.delete_index("articles")

    assert client.deleted_indexes == ["articles"]


def test_given_soft_deleted_instance_when_make_unsearchable_runs_then_deleted(
    adapter: FakeAdapter,
) -> None:
    deleted_article = Article(
        id=3, title="Archived Article", body="Old content", deleted_at="2020-01-01"
    )
    client = FakeMeilisearchClient()
    engine = MeilisearchEngine(client=client)
    config = FictionScoutConfig(driver="meilisearch")
    engine_manager = EngineManager(config)
    engine_manager.extend("meilisearch", lambda: engine)
    dispatcher = SpyDispatcher()

    orchestration.make_unsearchable(
        [deleted_article],
        adapter=adapter,
        engine_manager=engine_manager,
        dispatcher=dispatcher,
    )

    assert client.deleted == [("articles", [3])]


def test_given_meilisearch_extra_missing_when_constructed_then_raises_clear_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _boom(feature: str, module_name: str, extra: str) -> None:
        raise MissingDependencyError(feature=feature, package=module_name, extra=extra)

    monkeypatch.setattr("fiction_scout.engines.meilisearch.require_installed", _boom)

    with pytest.raises(MissingDependencyError) as excinfo:
        MeilisearchEngine()

    message = str(excinfo.value)
    assert "meilisearch" in message
    assert 'pip install "fiction-scout[meilisearch]"' in message


def test_given_meilisearch_configured_with_credentials_when_resolved_then_builds() -> (
    None
):
    manager = EngineManager(
        FictionScoutConfig(
            driver="meilisearch",
            extra={
                "meilisearch_url": "http://localhost:7700",
                "meilisearch_api_key": "test-key",
            },
        )
    )

    engine = manager.driver()

    assert isinstance(engine, MeilisearchEngine)
