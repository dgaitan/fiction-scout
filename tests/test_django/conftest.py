from __future__ import annotations

from collections.abc import Iterator

import pytest

from fiction_scout.adapters.django import runtime
from fiction_scout.config import FictionScoutConfig
from fiction_scout.engines.manager import EngineManager
from fiction_scout.sync.dispatcher import SyncDispatcher
from tests.support import FakeAlgoliaClient, FakeMeilisearchClient, SpyEngine

# `algolia`/`meilisearch`-marked fixtures below import their respective
# `fiction_scout.engines.*` modules, which require the matching optional
# package — safe at module import time because this whole `tests/test_django/`
# directory is only ever collected when `DJANGO_SETTINGS_MODULE` is set, and
# `test_django`'s nox session installs both the `algolia` and `meilisearch`
# extras alongside `django` for exactly this reason.


@pytest.fixture
def spy_engine(monkeypatch: pytest.MonkeyPatch) -> Iterator[SpyEngine]:
    engine = SpyEngine()
    manager = EngineManager(FictionScoutConfig(driver="spy"))
    manager.extend("spy", lambda: engine)
    monkeypatch.setattr(runtime, "_engine_manager", manager)
    monkeypatch.setattr(runtime, "_dispatcher", SyncDispatcher())
    yield engine


@pytest.fixture
def algolia_client(monkeypatch: pytest.MonkeyPatch) -> Iterator[FakeAlgoliaClient]:
    from fiction_scout.engines.algolia import AlgoliaEngine

    client = FakeAlgoliaClient()
    engine = AlgoliaEngine(client=client)
    manager = EngineManager(FictionScoutConfig(driver="algolia"))
    manager.extend("algolia", lambda: engine)
    monkeypatch.setattr(runtime, "_engine_manager", manager)
    monkeypatch.setattr(runtime, "_dispatcher", SyncDispatcher())
    yield client


@pytest.fixture
def meilisearch_client(
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[FakeMeilisearchClient]:
    from fiction_scout.engines.meilisearch import MeilisearchEngine

    client = FakeMeilisearchClient()
    engine = MeilisearchEngine(client=client)
    manager = EngineManager(FictionScoutConfig(driver="meilisearch"))
    manager.extend("meilisearch", lambda: engine)
    monkeypatch.setattr(runtime, "_engine_manager", manager)
    monkeypatch.setattr(runtime, "_dispatcher", SyncDispatcher())
    yield client
