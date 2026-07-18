from __future__ import annotations

from typing import Any, ClassVar

from django.db import models
from django.forms.models import model_to_dict

from fiction_scout import orchestration
from fiction_scout.adapters.django import runtime
from fiction_scout.engines.manager import EngineManager
from fiction_scout.protocols import Dispatcher, SearchableAdapter
from fiction_scout.search.builder import Builder


class SearchableMixin(models.Model):
    """Adds fiction-scout's public search surface to a Django model.

    Delegates all sync/dispatch/search orchestration to
    `fiction_scout.orchestration` — never reimplements it. Mirrors the
    SQLAlchemy mixin's method surface (`to_searchable_array`,
    `searchable_as`, `get_scout_key`, `.search()`, `.searchable()`,
    `.unsearchable()`, `should_be_searchable`).
    """

    soft_delete_field: ClassVar[str | None] = None

    class Meta:
        abstract = True

    @classmethod
    def searchable_as(cls) -> str:
        return cls._meta.db_table

    def get_scout_key(self) -> Any:
        return self.pk

    @classmethod
    def get_scout_key_name(cls) -> str:
        return cls._meta.pk.name

    def to_searchable_array(self) -> dict[str, Any]:
        # `model_to_dict` omits the primary key when it's an AutoField
        # (Field.editable=False) — override this method to include it.
        return model_to_dict(self)

    def should_be_searchable(self) -> bool:
        return orchestration.should_be_searchable(self, adapter=runtime.get_adapter())

    @classmethod
    def get_scout_adapter(cls) -> SearchableAdapter:
        return runtime.get_adapter()

    @classmethod
    def get_scout_engine_manager(cls) -> EngineManager:
        return runtime.get_engine_manager()

    @classmethod
    def get_scout_dispatcher(cls) -> Dispatcher:
        return runtime.get_dispatcher()

    @classmethod
    def search(cls, term: str = "", **kwargs: Any) -> Builder:
        return orchestration.perform_search(
            cls,
            term,
            adapter=runtime.get_adapter(),
            engine_manager=runtime.get_engine_manager(),
            **kwargs,
        )

    def searchable(self) -> None:
        orchestration.make_searchable(
            [self],
            adapter=runtime.get_adapter(),
            engine_manager=runtime.get_engine_manager(),
            dispatcher=runtime.get_dispatcher(),
        )

    def unsearchable(self) -> None:
        orchestration.make_unsearchable(
            [self],
            adapter=runtime.get_adapter(),
            engine_manager=runtime.get_engine_manager(),
            dispatcher=runtime.get_dispatcher(),
        )
