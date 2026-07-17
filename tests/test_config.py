from __future__ import annotations

import pytest

from fiction_scout.config import FictionScoutConfig, resolve_config


def test_defaults_when_nothing_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("FICTION_SCOUT_DRIVER", raising=False)
    config = resolve_config()
    assert config == FictionScoutConfig()
    assert config.driver == "database"
    assert config.soft_delete is False
    assert config.chunk_size == 500


def test_explicit_config_always_wins(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FICTION_SCOUT_DRIVER", "collection")
    explicit = FictionScoutConfig(driver="database")
    assert resolve_config(explicit) is explicit


def test_environment_variables_are_read(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FICTION_SCOUT_DRIVER", "collection")
    monkeypatch.setenv("FICTION_SCOUT_SOFT_DELETE", "true")
    monkeypatch.setenv("FICTION_SCOUT_CHUNK_SIZE", "50")
    monkeypatch.setenv("FICTION_SCOUT_QUEUE", "true")
    monkeypatch.setenv("FICTION_SCOUT_INDEX_PREFIX", "test_")

    config = resolve_config()

    assert config.driver == "collection"
    assert config.soft_delete is True
    assert config.chunk_size == 50
    assert config.queue is True
    assert config.index_prefix == "test_"


def test_with_overrides_returns_a_new_config(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("FICTION_SCOUT_DRIVER", raising=False)
    base = FictionScoutConfig()
    overridden = base.with_overrides(driver="collection")
    assert overridden.driver == "collection"
    assert base.driver == "database"
