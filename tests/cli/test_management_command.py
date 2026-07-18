from __future__ import annotations

import pytest
from click.testing import CliRunner
from django.core.management import call_command
from django.core.management.base import CommandError

from fiction_scout.cli.main import cli
from tests.django_app.models import Article
from tests.support import SpyEngine

pytestmark = [pytest.mark.django, pytest.mark.django_db]


def test_given_same_model_when_import_run_via_cli_and_management_command_then_identical(
    spy_engine: SpyEngine,
) -> None:
    Article.objects.create(title="Star Trek II", body="The Wrath of Khan")
    Article.objects.create(title="Star Wars", body="A New Hope")

    spy_engine.updated_batches.clear()
    result = CliRunner().invoke(cli, ["import", "tests.django_app.models.Article"])
    assert result.exit_code == 0
    via_cli = sorted(
        instance.to_searchable_array()["title"]
        for batch in spy_engine.updated_batches
        for instance in batch
    )

    spy_engine.updated_batches.clear()
    call_command("fiction_scout", "import", "tests.django_app.models.Article")
    via_management_command = sorted(
        instance.to_searchable_array()["title"]
        for batch in spy_engine.updated_batches
        for instance in batch
    )

    assert via_cli == via_management_command == ["Star Trek II", "Star Wars"]


def test_given_invalid_subcommand_when_management_command_runs_then_raises_error() -> (
    None
):
    with pytest.raises(CommandError):
        call_command("fiction_scout", "bogus", "tests.django_app.models.Article")


def test_given_bogus_dotted_path_when_management_command_import_runs_then_raises(
    spy_engine: SpyEngine,
) -> None:
    with pytest.raises(CommandError, match="Could not import"):
        call_command("fiction_scout", "import", "tests.django_app.models.NoSuchModel")
