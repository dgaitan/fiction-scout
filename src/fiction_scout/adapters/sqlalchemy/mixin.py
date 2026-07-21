from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar, cast

from sqlalchemy import inspect

from fiction_scout import orchestration
from fiction_scout.adapters.sqlalchemy import runtime
from fiction_scout.engines.manager import EngineManager
from fiction_scout.protocols import Dispatcher, SearchableAdapter
from fiction_scout.search.builder import Builder

if TYPE_CHECKING:
    from sqlalchemy.orm import Mapper


class SearchableMixin:
    """Adds fiction-scout's public search surface to a SQLAlchemy model.

    Delegates all sync/dispatch/search orchestration to
    `fiction_scout.orchestration` — never reimplements it. Mirrors the
    Django mixin's method surface (`to_searchable_array`, `searchable_as`,
    `get_scout_key`, `.search()`, `.searchable()`, `.unsearchable()`,
    `should_be_searchable`) — see
    `tests/test_sqlalchemy/test_events.py`'s parity test. A plain mixin, not
    itself a `DeclarativeBase` — models multiply-inherit it alongside their
    own declarative base, since SQLAlchemy has no single shared model base
    the way Django's `models.Model` provides.
    """

    soft_delete_field: ClassVar[str | None] = None

    @classmethod
    def searchable_as(cls) -> str:
        return cls.__tablename__  # type: ignore[attr-defined,no-any-return]

    def get_scout_key(self) -> Any:
        return getattr(self, type(self).get_scout_key_name())

    @classmethod
    def get_scout_key_name(cls) -> str:
        mapper = cast("Mapper[Any]", inspect(cls))
        column = mapper.primary_key[0]
        return str(mapper.get_property_by_column(column).key)

    def to_searchable_array(self) -> dict[str, Any]:
        mapper = cast("Mapper[Any]", inspect(type(self)))
        return {attr.key: getattr(self, attr.key) for attr in mapper.column_attrs}

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
