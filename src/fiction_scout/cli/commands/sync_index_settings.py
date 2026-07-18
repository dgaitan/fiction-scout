from __future__ import annotations

from fiction_scout.cli.model_resolution import resolve_model


def run_sync_index_settings(model_path: str) -> None:
    """Apply the configured index settings for the model at `model_path`.

    Settings come from `EngineManager.config.extra` — the same place any
    driver-specific configuration already lives (see `config.py`). Raises
    `IndexSettingsNotSupportedError` when the resolved driver has no
    settings API to apply to (see `Engine.update_index_settings`'s default).
    """
    model = resolve_model(model_path)
    engine_manager = model.get_scout_engine_manager()
    engine = engine_manager.driver()
    engine.update_index_settings(
        model, model.get_scout_adapter(), **engine_manager.config.extra
    )
