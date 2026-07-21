from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from fiction_scout.adapters.sqlalchemy.adapter import SQLAlchemyAdapter
from fiction_scout.config import FictionScoutConfig, resolve_config
from fiction_scout.engines.manager import EngineManager
from fiction_scout.sync.dispatcher import SyncDispatcher

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

# Unlike Django's `runtime.py`, `_adapter`/`_engine_manager` can't lazily
# self-construct on first access — there's no Django-settings-style implicit
# registry to discover a database connection from. `configure()` is the
# one-time entry point an app calls at startup (mirrors handing
# `sessionmaker(bind=engine)` to whatever needs it); `get_adapter()`/
# `get_engine_manager()` raise a clear error if called first.
_adapter: SQLAlchemyAdapter | None = None
_engine_manager: EngineManager | None = None
_dispatcher: SyncDispatcher | None = None


def configure(
    *,
    session_factory: Callable[[], Session],
    config: FictionScoutConfig | None = None,
) -> None:
    """Wire fiction-scout to a SQLAlchemy session factory.

    Call this once at app startup, after building a `sessionmaker`. Also
    connects the `before_commit`/`after_commit` session-event listeners
    (`adapters/sqlalchemy/events.py`) — the SQLAlchemy equivalent of
    Django's `AppConfig.ready()` wiring up `post_save`/`post_delete`.
    """
    global _adapter, _engine_manager

    from fiction_scout.adapters.sqlalchemy import events

    _adapter = SQLAlchemyAdapter(session_factory)
    _engine_manager = EngineManager(resolve_config(config))
    events.connect_events()


def get_adapter() -> SQLAlchemyAdapter:
    if _adapter is None:
        raise RuntimeError(
            "fiction_scout.adapters.sqlalchemy.runtime.configure() must be "
            "called before using a SearchableMixin model."
        )
    return _adapter


def get_engine_manager() -> EngineManager:
    if _engine_manager is None:
        raise RuntimeError(
            "fiction_scout.adapters.sqlalchemy.runtime.configure() must be "
            "called before using a SearchableMixin model."
        )
    return _engine_manager


def get_dispatcher() -> SyncDispatcher:
    global _dispatcher
    if _dispatcher is None:
        _dispatcher = SyncDispatcher()
    return _dispatcher
