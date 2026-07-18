from __future__ import annotations

from collections.abc import Iterator

import pytest

from fiction_scout.adapters.django import runtime
from fiction_scout.config import FictionScoutConfig
from fiction_scout.engines.manager import EngineManager
from fiction_scout.sync.dispatcher import SyncDispatcher
from tests.support import FakeAlgoliaClient, SpyEngine

# `algolia`-marked fixtures below import `fiction_scout.engines.algolia`,
# which requires the `algoliasearch` package — safe at module import time
# because this whole `tests/test_django/` directory is only ever collected
# when `DJANGO_SETTINGS_MODULE` is set, and `test_django`'s nox session
# installs the `algolia` extra alongside `django` for exactly this reason.


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
