from __future__ import annotations

from typing import Any, Callable

from django.core.management.base import BaseCommand, CommandError, CommandParser

from fiction_scout.cli.commands import (
    flush,
    import_cmd,
    queue_import,
    sync_index_settings,
)
from fiction_scout.exceptions import FictionScoutError

_SUBCOMMANDS: dict[str, Callable[[str], None]] = {
    "import": import_cmd.run_import,
    "queue-import": queue_import.run_queue_import,
    "flush": flush.run_flush,
    "sync-index-settings": sync_index_settings.run_sync_index_settings,
}


class Command(BaseCommand):
    """`manage.py fiction_scout <subcommand> <model>` — parses arguments only.

    Delegates every subcommand to the exact same `cli/commands/*.py`
    functions the standalone CLI calls, so the two entry points can never
    drift apart.
    """

    help = "Sync searchable models to a search index."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("subcommand", choices=sorted(_SUBCOMMANDS))
        parser.add_argument("model")

    def handle(self, *args: Any, **options: Any) -> None:
        run = _SUBCOMMANDS[options["subcommand"]]
        try:
            run(options["model"])
        except FictionScoutError as exc:
            raise CommandError(str(exc)) from exc
