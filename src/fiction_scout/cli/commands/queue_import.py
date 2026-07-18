from __future__ import annotations

from fiction_scout import orchestration
from fiction_scout.cli.model_resolution import resolve_model


def run_queue_import(model_path: str) -> None:
    """Import the model at `model_path` through its configured dispatcher.

    Unlike `import`, this does not force synchronous execution — if the
    model's dispatcher is an async/queue backend, the import runs there
    instead of blocking the CLI process.
    """
    model = resolve_model(model_path)
    orchestration.make_all_searchable(
        model,
        adapter=model.get_scout_adapter(),
        engine_manager=model.get_scout_engine_manager(),
        dispatcher=model.get_scout_dispatcher(),
    )
