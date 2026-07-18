from __future__ import annotations

from fiction_scout.cli.model_resolution import resolve_model


def run_flush(model_path: str) -> None:
    """Remove every index entry for the model at `model_path`.

    Only the index is affected — the model's own rows are never touched.
    """
    model = resolve_model(model_path)
    engine = model.get_scout_engine_manager().driver()
    engine.flush(model, model.get_scout_adapter())
