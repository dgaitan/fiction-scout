from __future__ import annotations

from fiction_scout import orchestration
from fiction_scout.cli.model_resolution import resolve_model
from fiction_scout.sync.dispatcher import SyncDispatcher


def run_import(model_path: str) -> None:
    """Push every existing row of the model at `model_path` into its index.

    Always runs synchronously via a `SyncDispatcher`, ignoring whatever
    dispatcher the model has configured — an operator running `import`
    wants the command to not exit until the index is populated. Use
    `queue-import` to route through the configured (possibly async)
    dispatcher instead.
    """
    model = resolve_model(model_path)
    orchestration.make_all_searchable(
        model,
        adapter=model.get_scout_adapter(),
        engine_manager=model.get_scout_engine_manager(),
        dispatcher=SyncDispatcher(),
    )
