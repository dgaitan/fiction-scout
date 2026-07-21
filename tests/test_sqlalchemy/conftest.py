from __future__ import annotations

from collections.abc import Iterator
from typing import TYPE_CHECKING

import pytest

from fiction_scout.config import FictionScoutConfig
from fiction_scout.engines.manager import EngineManager
from fiction_scout.sync.dispatcher import SyncDispatcher
from tests.support import SpyEngine

if TYPE_CHECKING:
    from sqlalchemy import Engine
    from sqlalchemy.orm import Session, sessionmaker

# `tests/conftest.py`'s `collect_ignore` keeps `tests/test_sqlalchemy/`'s test
# *files* out of collection when sqlalchemy isn't installed, but pytest still
# imports this directory's own `conftest.py` unconditionally while walking
# `testpaths` — collect_ignore doesn't reach conftest loading (same gap
# `tests/test_meilisearch/conftest.py` hit and fixed). A module-level
# `import sqlalchemy` here would break `nox -s test_core`'s isolated,
# extras-free venv. Every sqlalchemy-touching import below is deferred inside
# its fixture body instead.


@pytest.fixture
def engine() -> Iterator[Engine]:
    from sqlalchemy import create_engine

    from fiction_scout.adapters.sqlalchemy.adapter import register_sqlite_regexp
    from tests.sqlalchemy_app.models import Base

    eng = create_engine("sqlite:///:memory:")
    register_sqlite_regexp(eng)
    Base.metadata.create_all(eng)
    yield eng
    Base.metadata.drop_all(eng)
    eng.dispose()


@pytest.fixture
def session_factory(engine: Engine) -> sessionmaker[Session]:
    from sqlalchemy.orm import sessionmaker

    return sessionmaker(bind=engine)


@pytest.fixture
def spy_engine(
    session_factory: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch
) -> Iterator[SpyEngine]:
    from fiction_scout.adapters.sqlalchemy import runtime

    engine_double = SpyEngine()
    runtime.configure(session_factory=session_factory)
    manager = EngineManager(FictionScoutConfig(driver="spy"))
    manager.extend("spy", lambda: engine_double)
    monkeypatch.setattr(runtime, "_engine_manager", manager)
    monkeypatch.setattr(runtime, "_dispatcher", SyncDispatcher())
    yield engine_double
