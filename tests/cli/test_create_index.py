from __future__ import annotations

import pytest
from click.testing import CliRunner

from fiction_scout.cli.main import cli
from fiction_scout.config import FictionScoutConfig
from fiction_scout.engines.algolia import AlgoliaEngine
from fiction_scout.engines.manager import EngineManager
from tests.django_app.models import Article
from tests.support import FakeAlgoliaClient, SpyEngine

pytestmark = [pytest.mark.django, pytest.mark.django_db]


def test_given_driver_supports_it_when_create_index_runs_then_index_created(
    spy_engine: SpyEngine,
) -> None:
    result = CliRunner().invoke(
        cli, ["create-index", "tests.django_app.models.Article"]
    )

    assert result.exit_code == 0
    assert spy_engine.created_indexes == [Article.searchable_as()]


def test_given_algolia_driver_when_create_index_runs_then_clear_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from fiction_scout.adapters.django import runtime
    from fiction_scout.sync.dispatcher import SyncDispatcher

    engine = AlgoliaEngine(client=FakeAlgoliaClient())
    manager = EngineManager(FictionScoutConfig(driver="algolia-fake"))
    manager.extend("algolia-fake", lambda: engine)
    monkeypatch.setattr(runtime, "_engine_manager", manager)
    monkeypatch.setattr(runtime, "_dispatcher", SyncDispatcher())

    result = CliRunner().invoke(
        cli, ["create-index", "tests.django_app.models.Article"]
    )

    assert result.exit_code != 0
    assert "does not support create_index" in result.output


def test_given_bogus_dotted_path_when_create_index_runs_then_exits_nonzero() -> None:
    result = CliRunner().invoke(
        cli, ["create-index", "tests.django_app.models.NoSuchModel"]
    )

    assert result.exit_code != 0
    assert "Could not import" in result.output
