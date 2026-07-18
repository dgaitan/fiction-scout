from __future__ import annotations

import pytest
from click.testing import CliRunner

from fiction_scout.cli.main import cli
from tests.django_app.models import Article
from tests.support import SpyEngine

pytestmark = [pytest.mark.django, pytest.mark.django_db]


def test_given_driver_supports_it_when_delete_index_runs_then_index_deleted(
    spy_engine: SpyEngine,
) -> None:
    result = CliRunner().invoke(
        cli, ["delete-index", "tests.django_app.models.Article"]
    )

    assert result.exit_code == 0
    assert spy_engine.deleted_indexes == [Article.searchable_as()]


def test_given_bogus_dotted_path_when_delete_index_runs_then_exits_nonzero() -> None:
    result = CliRunner().invoke(
        cli, ["delete-index", "tests.django_app.models.NoSuchModel"]
    )

    assert result.exit_code != 0
    assert "Could not import" in result.output
