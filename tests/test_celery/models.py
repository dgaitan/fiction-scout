"""A `ScoutModel`-conforming test model, resolvable via dotted import path.

Mirrors `adapters/django/runtime.py`'s lazy-module-global pattern: tests
`monkeypatch.setattr` the two module globals below so the Celery worker-side
task (which only has a dotted model path, not a live adapter/engine_manager
reference) can resolve back to the exact `FakeAdapter`/`EngineManager` the
test constructed.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from fiction_scout.engines.manager import EngineManager
    from tests.support import FakeAdapter

_adapter: FakeAdapter | None = None
_engine_manager: EngineManager | None = None


@dataclass
class CeleryArticle:
    id: int
    title: str
    body: str
    deleted_at: str | None = None

    def to_searchable_array(self) -> dict[str, Any]:
        return {"id": self.id, "title": self.title, "body": self.body}

    @classmethod
    def get_scout_adapter(cls) -> FakeAdapter:
        assert _adapter is not None, "test must set tests.test_celery.models._adapter"
        return _adapter

    @classmethod
    def get_scout_engine_manager(cls) -> EngineManager:
        assert _engine_manager is not None, (
            "test must set tests.test_celery.models._engine_manager"
        )
        return _engine_manager
