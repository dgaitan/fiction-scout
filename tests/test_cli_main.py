from __future__ import annotations

from click.testing import CliRunner

from fiction_scout.cli.main import cli


def test_given_cli_group_when_help_invoked_then_lists_every_command() -> None:
    result = CliRunner().invoke(cli, ["--help"])

    assert result.exit_code == 0
    for name in ("import", "queue-import", "flush", "sync-index-settings"):
        assert name in result.output
