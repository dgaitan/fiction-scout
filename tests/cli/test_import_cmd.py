from __future__ import annotations

import pytest
from click.testing import CliRunner

from fiction_scout.adapters.django import runtime
from fiction_scout.cli.main import cli
from fiction_scout.config import FictionScoutConfig
from fiction_scout.engines.manager import EngineManager
from tests.django_app.models import Article
from tests.support import SpyDispatcher, SpyEngine

pytestmark = [pytest.mark.django, pytest.mark.django_db]


def test_given_existing_rows_when_import_runs_then_all_rows_pushed_to_engine(
    spy_engine: SpyEngine,
) -> None:
    Article.objects.create(title="Star Wars", body="A New Hope")
    Article.objects.create(title="Star Trek", body="The Wrath of Khan")
    spy_engine.updated_batches.clear()

    result = CliRunner().invoke(cli, ["import", "tests.django_app.models.Article"])

    assert result.exit_code == 0
    synced = {a.title for batch in spy_engine.updated_batches for a in batch}
    assert synced == {"Star Wars", "Star Trek"}


def test_given_bogus_dotted_path_when_import_runs_then_exits_nonzero() -> None:
    result = CliRunner().invoke(cli, ["import", "tests.django_app.models.NoSuchModel"])

    assert result.exit_code != 0
    assert "Could not import" in result.output


def test_given_configured_async_dispatcher_when_import_runs_then_bypasses_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = SpyEngine()
    manager = EngineManager(FictionScoutConfig(driver="spy"))
    manager.extend("spy", lambda: engine)
    dispatcher = SpyDispatcher()
    monkeypatch.setattr(runtime, "_engine_manager", manager)
    monkeypatch.setattr(runtime, "_dispatcher", dispatcher)
    Article.objects.create(title="Star Wars", body="A New Hope")
    dispatcher.dispatched_count = 0
    engine.updated_batches.clear()

    result = CliRunner().invoke(cli, ["import", "tests.django_app.models.Article"])

    assert result.exit_code == 0
    assert dispatcher.dispatched_count == 0
    assert engine.updated_batches
