from __future__ import annotations

from collections.abc import Iterator

import pytest

from fiction_scout.adapters.django import runtime
from fiction_scout.config import FictionScoutConfig
from fiction_scout.engines.manager import EngineManager
from fiction_scout.sync.dispatcher import SyncDispatcher
from tests.support import SpyEngine


@pytest.fixture
def spy_engine(monkeypatch: pytest.MonkeyPatch) -> Iterator[SpyEngine]:
    engine = SpyEngine()
    manager = EngineManager(FictionScoutConfig(driver="spy"))
    manager.extend("spy", lambda: engine)
    monkeypatch.setattr(runtime, "_engine_manager", manager)
    monkeypatch.setattr(runtime, "_dispatcher", SyncDispatcher())
    yield engine
