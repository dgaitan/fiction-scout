from __future__ import annotations

from collections.abc import Iterator
from typing import Any

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


class SettingsEngine(SpyEngine):
    """A `SpyEngine` that supports index settings, unlike the base default."""

    def __init__(self) -> None:
        super().__init__()
        self.settings_calls: list[dict[str, Any]] = []

    def update_index_settings(self, model: type, adapter: Any, **settings: Any) -> None:
        self.settings_calls.append(settings)


@pytest.fixture
def settings_engine(monkeypatch: pytest.MonkeyPatch) -> Iterator[SettingsEngine]:
    engine = SettingsEngine()
    manager = EngineManager(
        FictionScoutConfig(driver="spy", extra={"searchable_attributes": ["title"]})
    )
    manager.extend("spy", lambda: engine)
    monkeypatch.setattr(runtime, "_engine_manager", manager)
    monkeypatch.setattr(runtime, "_dispatcher", SyncDispatcher())
    yield engine
