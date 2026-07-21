from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from fiction_scout import orchestration
from fiction_scout.config import FictionScoutConfig
from fiction_scout.engines.algolia import AlgoliaEngine
from fiction_scout.engines.manager import EngineManager
from fiction_scout.exceptions import (
    EngineAuthenticationError,
    EngineConnectionError,
    IndexCreationNotSupportedError,
    MissingCredentialsError,
    MissingDependencyError,
    UnfilterableAttributeError,
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


def test_given_index_prefix_when_update_called_then_prefixed_index_name_used(
    articles: list[Article], adapter: FakeAdapter
) -> None:
    client = FakeAlgoliaClient()
    engine = AlgoliaEngine(client=client, index_prefix="tenant_a_")

    engine.update([articles[0]], adapter)

    index_name, _ = client.saved[0]
    assert index_name == "tenant_a_articles"


def test_given_index_prefix_when_delete_and_flush_called_then_prefixed_index_name_used(
    articles: list[Article], adapter: FakeAdapter
) -> None:
    client = FakeAlgoliaClient()
    engine = AlgoliaEngine(client=client, index_prefix="tenant_a_")

    engine.delete([articles[0]], adapter)
    engine.flush(Article, adapter)

    assert client.deleted == [("tenant_a_articles", ["1"])]
    assert client.cleared == ["tenant_a_articles"]


def test_given_index_prefix_when_search_called_then_prefixed_index_name_used(
    adapter: FakeAdapter,
) -> None:
    client = FakeAlgoliaClient()
    engine = AlgoliaEngine(client=client, index_prefix="tenant_a_")
    builder = Builder(Article, "star", engine=engine, adapter=adapter)

    builder.raw()

    index_name, _ = client.search_calls[0]
    assert index_name == "tenant_a_articles"


def test_given_within_override_when_search_called_then_prefix_not_applied(
    adapter: FakeAdapter,
) -> None:
    client = FakeAlgoliaClient()
    engine = AlgoliaEngine(client=client, index_prefix="tenant_a_")
    builder = Builder(Article, "star", engine=engine, adapter=adapter).within(
        "custom_index"
    )

    builder.raw()

    index_name, _ = client.search_calls[0]
    assert index_name == "custom_index"


def test_given_no_where_clauses_when_search_called_then_no_filters_key_sent(
    adapter: FakeAdapter,
) -> None:
    client = FakeAlgoliaClient()
    engine = AlgoliaEngine(client=client)
    builder = Builder(Article, "star", engine=engine, adapter=adapter)

    builder.raw()

    _, params = client.search_calls[0]
    assert "filters" not in params


def test_given_where_clause_when_search_called_then_filters_translated(
    adapter: FakeAdapter,
) -> None:
    client = FakeAlgoliaClient()
    engine = AlgoliaEngine(client=client)
    builder = Builder(Article, "star", engine=engine, adapter=adapter).where(
        "status", "published"
    )

    builder.raw()

    _, params = client.search_calls[0]
    assert params["filters"] == "status:'published'"


def test_given_where_in_clause_when_search_called_then_filters_translated(
    adapter: FakeAdapter,
) -> None:
    client = FakeAlgoliaClient()
    engine = AlgoliaEngine(client=client)
    builder = Builder(Article, "star", engine=engine, adapter=adapter).where_in(
        "category", ["scifi", "action"]
    )

    builder.raw()

    _, params = client.search_calls[0]
    assert params["filters"] == "(category:'scifi' OR category:'action')"


def test_given_empty_where_in_when_search_called_then_always_false_sentinel_used(
    adapter: FakeAdapter,
) -> None:
    client = FakeAlgoliaClient()
    engine = AlgoliaEngine(client=client)
    builder = Builder(Article, "star", engine=engine, adapter=adapter).where_in(
        "category", []
    )

    builder.raw()

    _, params = client.search_calls[0]
    assert params["filters"] == "0:1"


def test_given_where_not_in_clause_when_search_called_then_filters_translated(
    adapter: FakeAdapter,
) -> None:
    client = FakeAlgoliaClient()
    engine = AlgoliaEngine(client=client)
    builder = Builder(Article, "star", engine=engine, adapter=adapter).where_not_in(
        "category", ["horror"]
    )

    builder.raw()

    _, params = client.search_calls[0]
    assert params["filters"] == "(NOT category:'horror')"


def test_given_combined_where_clauses_when_search_called_then_joined_with_and(
    adapter: FakeAdapter,
) -> None:
    client = FakeAlgoliaClient()
    engine = AlgoliaEngine(client=client)
    builder = (
        Builder(Article, "star", engine=engine, adapter=adapter)
        .where("status", "published")
        .where_in("category", ["scifi"])
    )

    builder.raw()

    _, params = client.search_calls[0]
    assert params["filters"] == "status:'published' AND (category:'scifi')"


def test_given_known_settings_when_update_settings_called_then_set_settings_invoked(
    adapter: FakeAdapter,
) -> None:
    client = FakeAlgoliaClient()
    engine = AlgoliaEngine(client=client)

    engine.update_index_settings(
        Article,
        adapter,
        searchable_attributes=["title", "body"],
        custom_ranking=["desc(views)"],
    )

    assert client.settings_updated == [
        (
            "articles",
            {
                "searchableAttributes": ["title", "body"],
                "customRanking": ["desc(views)"],
            },
        )
    ]


def test_given_unrelated_config_keys_when_update_index_settings_called_then_ignored(
    adapter: FakeAdapter,
) -> None:
    client = FakeAlgoliaClient()
    engine = AlgoliaEngine(client=client)

    engine.update_index_settings(
        Article,
        adapter,
        meilisearch_url="http://localhost:7700",
        algolia_app_id="unrelated",
    )

    assert client.settings_updated == []


def test_given_index_prefix_when_update_index_settings_called_then_prefixed_index_used(
    adapter: FakeAdapter,
) -> None:
    client = FakeAlgoliaClient()
    engine = AlgoliaEngine(client=client, index_prefix="tenant_a_")

    engine.update_index_settings(Article, adapter, searchable_attributes=["title"])

    index_name, _ = client.settings_updated[0]
    assert index_name == "tenant_a_articles"


def test_given_index_prefix_in_config_when_resolved_then_prefix_wired() -> None:
    manager = EngineManager(
        FictionScoutConfig(
            driver="algolia",
            index_prefix="tenant_a_",
            extra={"algolia_app_id": "test-app", "algolia_api_key": "test-key"},
        )
    )

    engine = manager.driver()

    assert isinstance(engine, AlgoliaEngine)
    assert engine._index_prefix == "tenant_a_"


def test_given_blank_app_id_when_engine_constructed_then_raises_missing_creds() -> None:
    with pytest.raises(MissingCredentialsError) as excinfo:
        AlgoliaEngine(app_id="", api_key="test-key")

    assert excinfo.value.missing == ["algolia_app_id"]


def test_given_blank_api_key_when_engine_constructed_then_raises_missing_creds() -> (
    None
):
    with pytest.raises(MissingCredentialsError) as excinfo:
        AlgoliaEngine(app_id="test-app", api_key="")

    assert excinfo.value.missing == ["algolia_api_key"]


def test_given_401_response_when_update_called_then_raises_engine_authentication_error(
    articles: list[Article], adapter: FakeAdapter
) -> None:
    from algoliasearch.http.exceptions import RequestException

    client = FakeAlgoliaClient(raises=RequestException("Invalid API key", 401))
    engine = AlgoliaEngine(client=client)

    with pytest.raises(EngineAuthenticationError) as excinfo:
        engine.update([articles[0]], adapter)

    assert "credentials were rejected" in str(excinfo.value)


def test_given_403_response_when_search_called_then_raises_engine_authentication_error(
    adapter: FakeAdapter,
) -> None:
    from algoliasearch.http.exceptions import RequestException

    client = FakeAlgoliaClient(raises=RequestException("Forbidden", 403))
    engine = AlgoliaEngine(client=client)
    builder = Builder(Article, "star", engine=engine, adapter=adapter)

    with pytest.raises(EngineAuthenticationError):
        builder.get()


def test_given_dns_resolution_failure_when_delete_called_then_raises_connection_error(
    articles: list[Article], adapter: FakeAdapter
) -> None:
    from requests.exceptions import ConnectionError as RequestsConnectionError

    client = FakeAlgoliaClient(raises=RequestsConnectionError("Failed to resolve host"))
    engine = AlgoliaEngine(client=client)

    with pytest.raises(EngineConnectionError) as excinfo:
        engine.delete([articles[0]], adapter)

    message = str(excinfo.value)
    assert "Could not reach" in message
    assert "algolia_app_id" in message


def test_given_unreachable_hosts_when_flush_called_then_raises_connection_error(
    adapter: FakeAdapter,
) -> None:
    from algoliasearch.http.exceptions import AlgoliaUnreachableHostException

    client = FakeAlgoliaClient(raises=AlgoliaUnreachableHostException("no hosts left"))
    engine = AlgoliaEngine(client=client)

    with pytest.raises(EngineConnectionError):
        engine.flush(Article, adapter)


def test_given_non_auth_request_exception_when_update_called_then_propagates(
    articles: list[Article], adapter: FakeAdapter
) -> None:
    from algoliasearch.http.exceptions import RequestException

    client = FakeAlgoliaClient(raises=RequestException("Bad request", 400))
    engine = AlgoliaEngine(client=client)

    with pytest.raises(RequestException):
        engine.update([articles[0]], adapter)


def test_given_undeclared_facet_attribute_when_search_called_then_raises_filter_error(
    adapter: FakeAdapter,
) -> None:
    from algoliasearch.http.exceptions import RequestException

    message = (
        "Invalid Filter syntax, the offending part is: 'status' isn't a "
        "faceted attribute, please use attributesForFaceting to declare it"
    )
    client = FakeAlgoliaClient(raises=RequestException(message, 400))
    engine = AlgoliaEngine(client=client)
    builder = Builder(Article, "star", engine=engine, adapter=adapter).where(
        "status", "published"
    )

    with pytest.raises(UnfilterableAttributeError) as excinfo:
        builder.get()

    assert "attributes_for_faceting" in str(excinfo.value)


def test_given_bad_request_without_faceting_hint_when_search_called_then_propagates(
    adapter: FakeAdapter,
) -> None:
    from algoliasearch.http.exceptions import RequestException

    client = FakeAlgoliaClient(raises=RequestException("Invalid query syntax", 400))
    engine = AlgoliaEngine(client=client)
    builder = Builder(Article, "star", engine=engine, adapter=adapter)

    with pytest.raises(RequestException):
        builder.get()
