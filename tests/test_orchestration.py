from __future__ import annotations

from fiction_scout import orchestration
from fiction_scout.config import FictionScoutConfig
from fiction_scout.engines.manager import EngineManager
from fiction_scout.search.builder import Builder
from fiction_scout.sync.context import without_syncing_to_search
from tests.support import Article, FakeAdapter, SpyDispatcher, SpyEngine


def _spy_engine_manager(engine: SpyEngine) -> EngineManager:
    manager = EngineManager(FictionScoutConfig(driver="spy"))
    manager.extend("spy", lambda: engine)
    return manager


def test_given_not_paused_when_make_searchable_called_then_engine_receives_batch(
    adapter: FakeAdapter, articles: list[Article]
) -> None:
    engine = SpyEngine()
    dispatcher = SpyDispatcher()
    batch = articles[:2]

    orchestration.make_searchable(
        batch,
        adapter=adapter,
        engine_manager=_spy_engine_manager(engine),
        dispatcher=dispatcher,
    )

    assert engine.updated_batches == [batch]


def test_given_syncing_paused_when_make_searchable_called_then_engine_not_touched(
    adapter: FakeAdapter, articles: list[Article]
) -> None:
    engine = SpyEngine()
    dispatcher = SpyDispatcher()

    with without_syncing_to_search():
        orchestration.make_searchable(
            articles[:2],
            adapter=adapter,
            engine_manager=_spy_engine_manager(engine),
            dispatcher=dispatcher,
        )

    assert engine.updated_batches == []


def test_given_non_searchable_instance_when_searchable_called_then_excluded_from_batch(
    adapter: FakeAdapter, articles: list[Article]
) -> None:
    engine = SpyEngine()
    dispatcher = SpyDispatcher()
    live, soft_deleted = articles[0], articles[2]  # articles[2] has deleted_at set

    orchestration.make_searchable(
        [live, soft_deleted],
        adapter=adapter,
        engine_manager=_spy_engine_manager(engine),
        dispatcher=dispatcher,
    )

    assert engine.updated_batches == [[live]]


def test_given_dispatcher_when_make_searchable_called_then_write_goes_through_dispatch(
    adapter: FakeAdapter, articles: list[Article]
) -> None:
    engine = SpyEngine()
    dispatcher = SpyDispatcher()

    orchestration.make_searchable(
        articles[:1],
        adapter=adapter,
        engine_manager=_spy_engine_manager(engine),
        dispatcher=dispatcher,
    )

    assert dispatcher.dispatched_count == 1
    assert engine.updated_batches == [articles[:1]]


def test_given_not_paused_when_make_unsearchable_called_then_engine_deletes_batch(
    adapter: FakeAdapter, articles: list[Article]
) -> None:
    engine = SpyEngine()
    dispatcher = SpyDispatcher()
    batch = articles[:2]

    orchestration.make_unsearchable(
        batch,
        adapter=adapter,
        engine_manager=_spy_engine_manager(engine),
        dispatcher=dispatcher,
    )

    assert engine.deleted_batches == [batch]


def test_given_syncing_paused_when_make_unsearchable_called_then_engine_not_touched(
    adapter: FakeAdapter, articles: list[Article]
) -> None:
    engine = SpyEngine()
    dispatcher = SpyDispatcher()

    with without_syncing_to_search():
        orchestration.make_unsearchable(
            articles[:2],
            adapter=adapter,
            engine_manager=_spy_engine_manager(engine),
            dispatcher=dispatcher,
        )

    assert engine.deleted_batches == []


def test_given_large_batch_when_make_searchable_then_dispatched_in_chunks() -> None:
    live_articles = [
        Article(id=i, title=f"Title {i}", body=f"Body {i}") for i in range(1, 5)
    ]
    adapter = FakeAdapter(live_articles)
    engine = SpyEngine()
    manager = EngineManager(FictionScoutConfig(driver="spy", chunk_size=2))
    manager.extend("spy", lambda: engine)
    dispatcher = SpyDispatcher()

    orchestration.make_searchable(
        live_articles,
        adapter=adapter,
        engine_manager=manager,
        dispatcher=dispatcher,
    )

    assert dispatcher.dispatched_count == 2
    assert engine.updated_batches == [live_articles[:2], live_articles[2:]]


def test_given_explicit_chunk_size_when_make_searchable_then_overrides_config() -> None:
    live_articles = [
        Article(id=i, title=f"Title {i}", body=f"Body {i}") for i in range(1, 5)
    ]
    adapter = FakeAdapter(live_articles)
    engine = SpyEngine()
    dispatcher = SpyDispatcher()

    orchestration.make_searchable(
        live_articles,
        adapter=adapter,
        engine_manager=_spy_engine_manager(engine),
        dispatcher=dispatcher,
        chunk_size=3,
    )

    assert dispatcher.dispatched_count == 2
    assert engine.updated_batches == [live_articles[:3], live_articles[3:]]


def test_given_large_batch_when_make_unsearchable_then_dispatched_in_chunks() -> None:
    articles_to_remove = [
        Article(id=i, title=f"Title {i}", body=f"Body {i}") for i in range(1, 5)
    ]
    adapter = FakeAdapter(articles_to_remove)
    engine = SpyEngine()
    manager = EngineManager(FictionScoutConfig(driver="spy", chunk_size=2))
    manager.extend("spy", lambda: engine)
    dispatcher = SpyDispatcher()

    orchestration.make_unsearchable(
        articles_to_remove,
        adapter=adapter,
        engine_manager=manager,
        dispatcher=dispatcher,
    )

    assert dispatcher.dispatched_count == 2
    assert engine.deleted_batches == [
        articles_to_remove[:2],
        articles_to_remove[2:],
    ]


def test_given_chunk_size_when_make_all_searchable_then_one_call_per_chunk() -> None:
    live_articles = [
        Article(id=i, title=f"Title {i}", body=f"Body {i}") for i in range(1, 5)
    ]
    adapter = FakeAdapter(live_articles)
    engine = SpyEngine()
    dispatcher = SpyDispatcher()

    orchestration.make_all_searchable(
        Article,
        adapter=adapter,
        engine_manager=_spy_engine_manager(engine),
        dispatcher=dispatcher,
        chunk_size=2,
    )

    assert len(engine.updated_batches) == 2
    assert engine.updated_batches[0] == live_articles[:2]
    assert engine.updated_batches[1] == live_articles[2:]


def test_given_no_chunk_size_when_make_all_searchable_then_uses_config_chunk_size() -> (
    None
):
    live_articles = [
        Article(id=i, title=f"Title {i}", body=f"Body {i}") for i in range(1, 5)
    ]
    adapter = FakeAdapter(live_articles)
    engine = SpyEngine()
    manager = EngineManager(FictionScoutConfig(driver="spy", chunk_size=2))
    manager.extend("spy", lambda: engine)
    dispatcher = SpyDispatcher()

    orchestration.make_all_searchable(
        Article,
        adapter=adapter,
        engine_manager=manager,
        dispatcher=dispatcher,
    )

    assert len(engine.updated_batches) == 2
    assert engine.updated_batches[0] == live_articles[:2]
    assert engine.updated_batches[1] == live_articles[2:]


def test_given_perform_search_called_then_returns_builder_bound_to_resolved_engine(
    adapter: FakeAdapter,
) -> None:
    engine = SpyEngine()

    builder = orchestration.perform_search(
        Article,
        "star",
        adapter=adapter,
        engine_manager=_spy_engine_manager(engine),
    )

    assert isinstance(builder, Builder)
    assert builder.engine is engine
    assert builder.adapter is adapter
    assert builder.term == "star"
    assert builder.model is Article
