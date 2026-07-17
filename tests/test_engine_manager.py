from __future__ import annotations

import pytest

from fiction_scout.config import FictionScoutConfig
from fiction_scout.engines.collection import CollectionEngine
from fiction_scout.engines.database import DatabaseEngine
from fiction_scout.engines.manager import EngineManager
from fiction_scout.exceptions import UnknownDriverError


def test_builtin_drivers_resolve() -> None:
    manager = EngineManager()
    assert isinstance(manager.driver("collection"), CollectionEngine)
    assert isinstance(manager.driver("database"), DatabaseEngine)


def test_driver_defaults_to_configured_driver() -> None:
    manager = EngineManager(FictionScoutConfig(driver="collection"))
    assert isinstance(manager.driver(), CollectionEngine)


def test_unknown_driver_raises_with_available_drivers_listed() -> None:
    manager = EngineManager()
    with pytest.raises(UnknownDriverError) as excinfo:
        manager.driver("algolia")
    assert "algolia" in str(excinfo.value)
    assert "collection" in str(excinfo.value)
    assert "database" in str(excinfo.value)


def test_extend_registers_a_custom_driver() -> None:
    manager = EngineManager()

    class CustomEngine(CollectionEngine):
        pass

    manager.extend("custom", CustomEngine)
    assert isinstance(manager.driver("custom"), CustomEngine)


def test_engines_are_cached_across_calls() -> None:
    manager = EngineManager()
    assert manager.driver("collection") is manager.driver("collection")


def test_forget_engines_forces_rebuild() -> None:
    manager = EngineManager()
    first = manager.driver("collection")
    manager.forget_engines()
    assert manager.driver("collection") is not first
