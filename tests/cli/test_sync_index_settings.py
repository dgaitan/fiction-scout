from __future__ import annotations

import pytest
from click.testing import CliRunner

from fiction_scout.cli.main import cli
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
