from __future__ import annotations

from fiction_scout.cli.model_resolution import resolve_model


def run_sync_index_settings(model_path: str) -> None:
    """Apply the configured index settings for the model at `model_path`.

    Settings come from `EngineManager.config.extra["index_settings"]`,
    keyed by the same dotted `model_path` used here — each model's index
    settings are isolated to that model, since `extra` is otherwise a
    single dict shared by every model in the process (see `config.py`) and
    settings like `attributes_for_faceting` are per-index, not global. A
    model with no entry gets an empty settings dict, which
    `update_index_settings` already no-ops on. Raises
    `IndexSettingsNotSupportedError` when the resolved driver has no
    settings API to apply to (see `Engine.update_index_settings`'s default).
    """
    model = resolve_model(model_path)
    engine_manager = model.get_scout_engine_manager()
    engine = engine_manager.driver()
    settings = engine_manager.config.extra.get("index_settings", {}).get(model_path, {})
    engine.update_index_settings(model, model.get_scout_adapter(), **settings)
