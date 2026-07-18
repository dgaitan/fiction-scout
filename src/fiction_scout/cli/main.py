"""fiction-scout's standalone CLI.

`manage.py fiction_scout` (the Django management command bridge) wraps these
exact command functions with argument parsing — it never reimplements them.
"""

from __future__ import annotations

from typing import Callable

import click

from fiction_scout.cli.commands import (
    flush,
    import_cmd,
    queue_import,
    sync_index_settings,
)
from fiction_scout.exceptions import FictionScoutError


def _run(fn: Callable[[str], None], model: str) -> None:
    try:
        fn(model)
    except FictionScoutError as exc:
        raise click.ClickException(str(exc)) from exc


@click.group()
def cli() -> None:
    """fiction-scout: sync searchable models to a search index."""


@cli.command(name="import")
@click.argument("model")
def import_command(model: str) -> None:
    """Push every existing row of MODEL into its configured search index."""
    _run(import_cmd.run_import, model)


@cli.command(name="queue-import")
@click.argument("model")
def queue_import_command(model: str) -> None:
    """Import MODEL via its configured dispatcher, not synchronously."""
    _run(queue_import.run_queue_import, model)


@cli.command(name="flush")
@click.argument("model")
def flush_command(model: str) -> None:
    """Remove every index entry for MODEL, leaving its rows untouched."""
    _run(flush.run_flush, model)


@cli.command(name="sync-index-settings")
@click.argument("model")
def sync_index_settings_command(model: str) -> None:
    """Apply MODEL's configured index settings to its search driver."""
    _run(sync_index_settings.run_sync_index_settings, model)
