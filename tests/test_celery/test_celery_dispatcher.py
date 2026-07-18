from __future__ import annotations

import pytest
from celery import Celery

from fiction_scout import orchestration
from fiction_scout.config import FictionScoutConfig
from fiction_scout.engines.manager import EngineManager
from fiction_scout.exceptions import MissingDependencyError
from fiction_scout.sync.dispatchers.celery import CeleryDispatcher
from tests.support import FakeAdapter, SpyEngine
from tests.test_celery import models

pytestmark = [pytest.mark.celery]


@pytest.fixture
def eager_app() -> Celery:
    app = Celery("fiction_scout_tests")
    app.conf.task_always_eager = True
    return app


def _engine_manager(
    engine: SpyEngine, *, chunk_size: int | None = None
) -> EngineManager:
    config = FictionScoutConfig(driver="spy", chunk_size=chunk_size or 500)
    manager = EngineManager(config)
    manager.extend("spy", lambda: engine)
    return manager


def test_given_eager_celery_when_make_searchable_dispatches_then_sync_runs(
    monkeypatch: pytest.MonkeyPatch, eager_app: Celery
) -> None:
    articles = [
        models.CeleryArticle(id=1, title="Star Trek II", body="The Wrath of Khan"),
        models.CeleryArticle(id=2, title="Star Wars", body="A New Hope"),
    ]
    adapter = FakeAdapter(articles)
    engine = SpyEngine()
    monkeypatch.setattr(models, "_adapter", adapter)
    monkeypatch.setattr(models, "_engine_manager", _engine_manager(engine))

    with eager_app:
        orchestration.make_searchable(
            articles,
            adapter=adapter,
            engine_manager=_engine_manager(engine),
            dispatcher=CeleryDispatcher(),
        )

    assert engine.updated_batches == [articles]


def test_given_batch_larger_than_chunk_size_when_dispatched_then_chunked_not_truncated(
    monkeypatch: pytest.MonkeyPatch, eager_app: Celery
) -> None:
    articles = [
        models.CeleryArticle(id=i, title=f"Title {i}", body=f"Body {i}")
        for i in range(1, 6)
    ]
    adapter = FakeAdapter(articles)
    engine = SpyEngine()
    manager = _engine_manager(engine, chunk_size=2)
    monkeypatch.setattr(models, "_adapter", adapter)
    monkeypatch.setattr(models, "_engine_manager", manager)

    with eager_app:
        orchestration.make_searchable(
            articles,
            adapter=adapter,
            engine_manager=manager,
            dispatcher=CeleryDispatcher(),
        )

    assert len(engine.updated_batches) == 3
    synced_ids = sorted(
        article.id for batch in engine.updated_batches for article in batch
    )
    assert synced_ids == [1, 2, 3, 4, 5]


def test_given_celery_extra_missing_when_dispatcher_constructed_then_raises_clear_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _boom(feature: str, module_name: str, extra: str) -> None:
        from fiction_scout.exceptions import MissingDependencyError as _Err

        raise _Err(feature=feature, package=module_name, extra=extra)

    monkeypatch.setattr(
        "fiction_scout.sync.dispatchers.celery.require_installed", _boom
    )

    with pytest.raises(MissingDependencyError) as excinfo:
        CeleryDispatcher()

    message = str(excinfo.value)
    assert "celery" in message
    assert 'pip install "fiction-scout[celery]"' in message
