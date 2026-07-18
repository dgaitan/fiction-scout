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
from tests.support import Article, FakeAdapter, SpyDispatcher

pytestmark = [pytest.mark.algolia]


@dataclass
class _Hit:
    object_id: str


@dataclass
class _SearchResponse:
    hits: list[_Hit]
    nb_hits: int


class _FakeAlgoliaClient:
    """A hand-rolled fake standing in for `algoliasearch`'s `SearchClientSync`.

    Matches this project's existing test-double style (`SpyEngine`,
    `FakeAdapter`) rather than `unittest.mock` — see the design-decision
    docstring in `engines/algolia.py`.
    """

    def __init__(
        self, *, search_hits: list[_Hit] | None = None, nb_hits: int = 0
    ) -> None:
        self.saved: list[tuple[str, list[dict[str, Any]]]] = []
        self.deleted: list[tuple[str, list[str]]] = []
        self.cleared: list[str] = []
        self.deleted_indexes: list[str] = []
        self.search_calls: list[tuple[str, dict[str, Any]]] = []
        self._search_hits = search_hits or []
        self._nb_hits = nb_hits

    def save_objects(self, *, index_name: str, objects: list[dict[str, Any]]) -> None:
        self.saved.append((index_name, list(objects)))

    def delete_objects(self, *, index_name: str, object_ids: list[str]) -> None:
        self.deleted.append((index_name, list(object_ids)))

    def clear_objects(self, *, index_name: str) -> None:
        self.cleared.append(index_name)

    def delete_index(self, *, index_name: str) -> None:
        self.deleted_indexes.append(index_name)

    def search_single_index(
        self, *, index_name: str, search_params: dict[str, Any]
    ) -> _SearchResponse:
        self.search_calls.append((index_name, dict(search_params)))
        return _SearchResponse(hits=self._search_hits, nb_hits=self._nb_hits)


@dataclass
class _BlankArticle:
    """A model whose `to_searchable_array()` is empty."""

    id: int

    def to_searchable_array(self) -> dict[str, Any]:
        return {}


def test_given_instances_when_update_called_then_save_objects_carries_object_id(
    articles: list[Article], adapter: FakeAdapter
) -> None:
    client = _FakeAlgoliaClient()
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
    client = _FakeAlgoliaClient()
    engine = AlgoliaEngine(client=client)

    engine.update([blank, keepable], fake_adapter)

    assert len(client.saved) == 1
    _, objects = client.saved[0]
    assert [record["objectID"] for record in objects] == ["1"]


def test_given_instances_when_delete_called_then_delete_objects_carries_scout_keys(
    articles: list[Article], adapter: FakeAdapter
) -> None:
    client = _FakeAlgoliaClient()
    engine = AlgoliaEngine(client=client)

    engine.delete([articles[0], articles[1]], adapter)

    assert client.deleted == [("articles", ["1", "2"])]


def test_given_flush_called_then_clear_objects_empties_only_that_models_index(
    adapter: FakeAdapter,
) -> None:
    client = _FakeAlgoliaClient()
    engine = AlgoliaEngine(client=client)

    engine.flush(Article, adapter)

    assert client.cleared == ["articles"]


def test_given_search_term_when_get_called_then_returns_model_instances(
    articles: list[Article], adapter: FakeAdapter
) -> None:
    client = _FakeAlgoliaClient(
        search_hits=[_Hit(object_id="1"), _Hit(object_id="2")], nb_hits=2
    )
    engine = AlgoliaEngine(client=client)
    builder = Builder(Article, "star", engine=engine, adapter=adapter)

    results = builder.get()

    assert results == [articles[0], articles[1]]
    index_name, params = client.search_calls[0]
    assert index_name == "articles"
    assert params["query"] == "star"


def test_given_create_index_called_then_raises_not_supported() -> None:
    engine = AlgoliaEngine(client=_FakeAlgoliaClient())

    with pytest.raises(IndexCreationNotSupportedError, match="algolia"):
        engine.create_index("articles")


def test_given_soft_deleted_instance_when_make_unsearchable_runs_then_deleted(
    adapter: FakeAdapter,
) -> None:
    deleted_article = Article(
        id=3, title="Archived Article", body="Old content", deleted_at="2020-01-01"
    )
    client = _FakeAlgoliaClient()
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
