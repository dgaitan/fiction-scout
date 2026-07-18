from __future__ import annotations

from fiction_scout.cli.model_resolution import resolve_model


def run_create_index(model_path: str) -> None:
    """Create the search index for the model at `model_path`, if the driver supports it.

    No-op for `database`/`collection` (no separate index to create). Raises
    `IndexCreationNotSupportedError` for drivers like Algolia that have no
    explicit index-creation API — see `Engine.create_index`.
    """
    model = resolve_model(model_path)
    engine = model.get_scout_engine_manager().driver()
    adapter = model.get_scout_adapter()
    engine.create_index(engine.index_name_for(model, adapter))
