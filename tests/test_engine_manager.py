from __future__ import annotations

import pytest

from fiction_scout.config import FictionScoutConfig
from fiction_scout.engines.collection import CollectionEngine
from fiction_scout.engines.database import DatabaseEngine
from fiction_scout.engines.manager import EngineManager
from fiction_scout.exceptions import MissingDependencyError, UnknownDriverError


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
        manager.driver("bogus-driver-name")
    message = str(excinfo.value)
    assert "bogus-driver-name" in message
    assert "collection" in message
    assert "database" in message
    # "algolia"/"meilisearch" are registered (lazy) driver names even
    # without their SDKs installed — only *selecting* one requires the
    # extra, not registration.
    assert "algolia" in message
    assert "meilisearch" in message


def test_algolia_driver_raises_missing_dependency_when_sdk_not_installed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Mocked, not environment-dependent — `test_all` installs every extra
    # together, so this can't rely on `algoliasearch` actually being absent
    # (same reasoning as the Celery dispatcher's equivalent test). What this
    # proves is that `.driver()` raises via `validate_dependency` *before*
    # ever importing `engines.algolia`, regardless of what's installed.
    def _boom(feature: str, module_name: str, extra: str) -> None:
        raise MissingDependencyError(feature=feature, package=module_name, extra=extra)

    monkeypatch.setattr("fiction_scout.engines.manager.require_installed", _boom)

    manager = EngineManager(FictionScoutConfig(driver="algolia"))
    with pytest.raises(MissingDependencyError) as excinfo:
        manager.driver()
    message = str(excinfo.value)
    assert "algoliasearch" in message
    assert 'pip install "fiction-scout[algolia]"' in message


def test_meilisearch_driver_raises_missing_dependency_when_sdk_not_installed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Mocked, not environment-dependent — same reasoning as the Algolia
    # equivalent test just above: `test_all` installs every extra together,
    # so this can't rely on `meilisearch` actually being absent.
    def _boom(feature: str, module_name: str, extra: str) -> None:
        raise MissingDependencyError(feature=feature, package=module_name, extra=extra)

    monkeypatch.setattr("fiction_scout.engines.manager.require_installed", _boom)

    manager = EngineManager(FictionScoutConfig(driver="meilisearch"))
    with pytest.raises(MissingDependencyError) as excinfo:
        manager.driver()
    message = str(excinfo.value)
    assert "meilisearch" in message
    assert 'pip install "fiction-scout[meilisearch]"' in message


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
