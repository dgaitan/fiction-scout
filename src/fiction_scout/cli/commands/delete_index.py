from __future__ import annotations

from fiction_scout.cli.model_resolution import resolve_model


def run_delete_index(model_path: str) -> None:
    """Delete the search index for the model at `model_path`.

    No-op for `database`/`collection` (no separate index to delete).
    """
    model = resolve_model(model_path)
    engine = model.get_scout_engine_manager().driver()
    adapter = model.get_scout_adapter()
    engine.delete_index(engine.index_name_for(model, adapter))
