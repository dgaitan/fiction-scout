from __future__ import annotations

from fiction_scout.adapters.django.adapter import DjangoAdapter
from fiction_scout.config import resolve_config
from fiction_scout.engines.manager import EngineManager
from fiction_scout.sync.dispatcher import SyncDispatcher

# Lazy module-level singletons, not `functools.lru_cache` — tests swap them
# directly (`monkeypatch.setattr(runtime, "_engine_manager", ...)`) so a
# custom-registered driver (via `EngineManager.extend()`) and a real
# `resolve_config()` read both survive across every `get_*()` call in a
# process, the way a real Django app's lifetime requires.
_adapter: DjangoAdapter | None = None
_engine_manager: EngineManager | None = None
_dispatcher: SyncDispatcher | None = None


def get_adapter() -> DjangoAdapter:
    global _adapter
    if _adapter is None:
        _adapter = DjangoAdapter()
    return _adapter


def get_engine_manager() -> EngineManager:
    global _engine_manager
    if _engine_manager is None:
        _engine_manager = EngineManager(resolve_config())
    return _engine_manager


def get_dispatcher() -> SyncDispatcher:
    global _dispatcher
    if _dispatcher is None:
        _dispatcher = SyncDispatcher()
    return _dispatcher
