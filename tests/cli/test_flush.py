from __future__ import annotations

import pytest
from click.testing import CliRunner

from fiction_scout.cli.main import cli
from tests.django_app.models import Article
from tests.support import SpyEngine

pytestmark = [pytest.mark.django, pytest.mark.django_db]


def test_given_existing_index_entries_when_flush_runs_then_removes_index_not_rows(
    spy_engine: SpyEngine,
) -> None:
    Article.objects.create(title="Star Wars", body="A New Hope")

    result = CliRunner().invoke(cli, ["flush", "tests.django_app.models.Article"])

    assert result.exit_code == 0
    assert spy_engine.flushed == [Article]
    assert Article.objects.count() == 1


def test_given_bogus_dotted_path_when_flush_runs_then_exits_nonzero() -> None:
    result = CliRunner().invoke(cli, ["flush", "tests.django_app.models.NoSuchModel"])

    assert result.exit_code != 0
    assert "Could not import" in result.output
