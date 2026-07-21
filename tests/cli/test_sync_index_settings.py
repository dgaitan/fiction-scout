from __future__ import annotations

import pytest
from click.testing import CliRunner

from fiction_scout.adapters.django import runtime
from fiction_scout.cli.main import cli
from fiction_scout.config import FictionScoutConfig
from fiction_scout.engines.manager import EngineManager
from fiction_scout.sync.dispatcher import SyncDispatcher
from tests.cli.conftest import SettingsEngine
from tests.support import SpyEngine

pytestmark = [pytest.mark.django, pytest.mark.django_db]


def test_given_driver_with_settings_support_when_sync_runs_then_settings_applied(
    settings_engine: SettingsEngine,
) -> None:
    result = CliRunner().invoke(
        cli, ["sync-index-settings", "tests.django_app.models.Article"]
    )

    assert result.exit_code == 0
    assert settings_engine.settings_calls == [{"searchable_attributes": ["title"]}]


def test_given_driver_without_settings_support_when_sync_runs_then_clear_error(
    spy_engine: SpyEngine,
) -> None:
    result = CliRunner().invoke(
        cli, ["sync-index-settings", "tests.django_app.models.Article"]
    )

    assert result.exit_code != 0
    assert "does not support index settings" in result.output


def test_given_settings_for_another_model_when_sync_runs_then_not_applied(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = SettingsEngine()
    manager = EngineManager(
        FictionScoutConfig(
            driver="spy",
            extra={
                "index_settings": {
                    "tests.django_app.models.Article": {
                        "searchable_attributes": ["title"]
                    },
                    "some.other.Model": {"filterable_attributes": ["name"]},
                }
            },
        )
    )
    manager.extend("spy", lambda: engine)
    monkeypatch.setattr(runtime, "_engine_manager", manager)
    monkeypatch.setattr(runtime, "_dispatcher", SyncDispatcher())

    result = CliRunner().invoke(
        cli, ["sync-index-settings", "tests.django_app.models.Article"]
    )

    assert result.exit_code == 0
    assert engine.settings_calls == [{"searchable_attributes": ["title"]}]


def test_given_no_settings_for_model_when_sync_runs_then_empty_settings_applied(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = SettingsEngine()
    manager = EngineManager(FictionScoutConfig(driver="spy"))
    manager.extend("spy", lambda: engine)
    monkeypatch.setattr(runtime, "_engine_manager", manager)
    monkeypatch.setattr(runtime, "_dispatcher", SyncDispatcher())

    result = CliRunner().invoke(
        cli, ["sync-index-settings", "tests.django_app.models.Article"]
    )

    assert result.exit_code == 0
    assert engine.settings_calls == [{}]
