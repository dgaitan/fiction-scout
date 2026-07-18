from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from fiction_scout import orchestration
from fiction_scout.config import FictionScoutConfig
from fiction_scout.engines.algolia import AlgoliaEngine
from fiction_scout.engines.manager import EngineManager
from fiction_scout.exceptions import (
    IndexCreationNotSupportedError,
    MissingDependencyError,
)
from fiction_scout.search.builder import Builder
from tests.support import (
    AlgoliaHit,
    Article,
    FakeAdapter,
    FakeAlgoliaClient,
    SpyDispatcher,
)

pytestmark = [pytest.mark.algolia]


@dataclass
class _BlankArticle:
    """A model whose `to_searchable_array()` is empty."""

    id: int

    def to_searchable_array(self) -> dict[str, Any]:
        return {}


def test_given_instances_when_update_called_then_save_objects_carries_object_id(
    articles: list[Article], adapter: FakeAdapter
) -> None:
    client = FakeAlgoliaClient()
    engine = AlgoliaEngine(client=client)

    engine.update([articles[0], articles[1]], adapter)

    assert len(client.saved) == 1
    index_name, objects = client.saved[0]
    assert index_name == "articles"
    assert objects == [
        {
            "id": 1,
            "title": "Star Trek II",
            "body": "The Wrath of Khan",
            "objectID": "1",
        },
        {"id": 2, "title": "Star Wars", "body": "A New Hope", "objectID": "2"},
    ]


def test_given_empty_searchable_array_when_update_called_then_excluded() -> None:
    blank = _BlankArticle(id=99)
    keepable = Article(id=1, title="Star Trek II", body="The Wrath of Khan")
    fake_adapter = FakeAdapter([blank, keepable])
    client = FakeAlgoliaClient()
    engine = AlgoliaEngine(client=client)

    engine.update([blank, keepable], fake_adapter)

    assert len(client.saved) == 1
    _, objects = client.saved[0]
    assert [record["objectID"] for record in objects] == ["1"]


def test_given_instances_when_delete_called_then_delete_objects_carries_scout_keys(
    articles: list[Article], adapter: FakeAdapter
) -> None:
    client = FakeAlgoliaClient()
    engine = AlgoliaEngine(client=client)

    engine.delete([articles[0], articles[1]], adapter)

    assert client.deleted == [("articles", ["1", "2"])]


def test_given_flush_called_then_clear_objects_empties_only_that_models_index(
    adapter: FakeAdapter,
) -> None:
    client = FakeAlgoliaClient()
    engine = AlgoliaEngine(client=client)

    engine.flush(Article, adapter)

    assert client.cleared == ["articles"]


def test_given_search_term_when_get_called_then_returns_model_instances(
    articles: list[Article], adapter: FakeAdapter
) -> None:
    client = FakeAlgoliaClient(
        search_hits=[AlgoliaHit(object_id="1"), AlgoliaHit(object_id="2")], nb_hits=2
    )
    engine = AlgoliaEngine(client=client)
    builder = Builder(Article, "star", engine=engine, adapter=adapter)

    results = builder.get()

    assert results == [articles[0], articles[1]]
    index_name, params = client.search_calls[0]
    assert index_name == "articles"
    assert params["query"] == "star"


def test_given_create_index_called_then_raises_not_supported() -> None:
    engine = AlgoliaEngine(client=FakeAlgoliaClient())

    with pytest.raises(IndexCreationNotSupportedError, match="algolia"):
        engine.create_index("articles")


def test_given_soft_deleted_instance_when_make_unsearchable_runs_then_deleted(
    adapter: FakeAdapter,
) -> None:
    deleted_article = Article(
        id=3, title="Archived Article", body="Old content", deleted_at="2020-01-01"
    )
    client = FakeAlgoliaClient()
    engine = AlgoliaEngine(client=client)
    config = FictionScoutConfig(driver="algolia")
    engine_manager = EngineManager(config)
    engine_manager.extend("algolia", lambda: engine)
    dispatcher = SpyDispatcher()

    orchestration.make_unsearchable(
        [deleted_article],
        adapter=adapter,
        engine_manager=engine_manager,
        dispatcher=dispatcher,
    )

    assert client.deleted == [("articles", ["3"])]


def test_given_algolia_extra_missing_when_engine_constructed_then_raises_clear_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _boom(feature: str, module_name: str, extra: str) -> None:
        raise MissingDependencyError(feature=feature, package=module_name, extra=extra)

    monkeypatch.setattr("fiction_scout.engines.algolia.require_installed", _boom)

    with pytest.raises(MissingDependencyError) as excinfo:
        AlgoliaEngine()

    message = str(excinfo.value)
    assert "algolia" in message
    assert 'pip install "fiction-scout[algolia]"' in message


def test_given_algolia_configured_with_credentials_when_resolved_then_builds() -> None:
    manager = EngineManager(
        FictionScoutConfig(
            driver="algolia",
            extra={"algolia_app_id": "test-app", "algolia_api_key": "test-key"},
        )
    )

    engine = manager.driver()

    assert isinstance(engine, AlgoliaEngine)
