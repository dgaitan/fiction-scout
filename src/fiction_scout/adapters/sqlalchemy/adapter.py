from __future__ import annotations

import itertools
import re
from collections.abc import Callable, Iterator, Sequence
from typing import TYPE_CHECKING, Any, cast

from sqlalchemy import String, Text, event, false, func, inspect, or_, select

from fiction_scout.strategies import SearchStrategy, get_column_strategies

if TYPE_CHECKING:
    from sqlalchemy import Select
    from sqlalchemy.engine import Engine
    from sqlalchemy.orm import Mapper, Session

    from fiction_scout.adapters.sqlalchemy.mixin import SearchableMixin

# `\b` is a word-boundary escape in Python's `re` (SQLite's REGEXP shells out
# to it, via `register_sqlite_regexp` below) and in MySQL's ICU-backed regex
# engine, but PostgreSQL's native ARE regex engine doesn't recognize `\b` as
# a boundary at all — it silently matches nothing. Postgres's own
# word-boundary escape is `\y`. Same finding as `DjangoAdapter`'s
# `_WORD_BOUNDARY_BY_VENDOR`, since both adapters ultimately hand the
# pattern to the same underlying database regex engines.
_WORD_BOUNDARY_BY_DIALECT = {"postgresql": r"\y"}
_DEFAULT_WORD_BOUNDARY = r"\b"


def register_sqlite_regexp(engine: Engine) -> None:
    """Register a Python `REGEXP` function on `engine`'s SQLite connections.

    Unlike Postgres/MySQL (where `Column.regexp_match()` compiles to a
    native operator with zero extra setup), SQLite ships no `REGEXP`
    function at all. Call this once against a SQLite engine before using the
    full-text search strategy against it — a real SQLite-backed app needs
    this too, not just tests. Not wired automatically inside
    `SQLAlchemyAdapter`'s constructor: registering a connection-level
    function as a side effect of building the adapter would be a surprising
    hidden action for apps that never touch full-text search.
    """

    @event.listens_for(engine, "connect")
    def _on_connect(dbapi_connection: Any, connection_record: Any) -> None:
        dbapi_connection.create_function("REGEXP", 2, _regexp)


def _regexp(pattern: str, value: str | None) -> bool:
    if value is None:
        return False
    return re.search(pattern, value) is not None


def _primary_key_attr(model: type) -> str:
    mapper = cast("Mapper[Any]", inspect(model))
    column = mapper.primary_key[0]
    return str(mapper.get_property_by_column(column).key)


def _entity(query: Select[Any]) -> Any:
    return query.column_descriptions[0]["entity"]


class SQLAlchemyAdapter:
    """Implements `SearchableAdapter` for SQLAlchemy models.

    Delegates model-specific behavior (`searchable_as`, `get_scout_key`,
    `to_searchable_array`) to the methods `SearchableMixin` puts on the
    model itself — mirrors `DjangoAdapter`. Unlike Django, SQLAlchemy has no
    implicit global connection to auto-discover, so this adapter is
    constructed with a `session_factory` (a plain `sessionmaker` instance
    already has exactly this zero-arg-callable-returns-a-Session shape) and
    opens its own short-lived session per query-building call.
    """

    def __init__(self, session_factory: Callable[[], Session]) -> None:
        self._session_factory = session_factory

    def searchable_as(self, model: type[SearchableMixin]) -> str:
        return model.searchable_as()

    def get_scout_key(self, instance: SearchableMixin) -> Any:
        return instance.get_scout_key()

    def get_scout_key_name(self, model: type[SearchableMixin]) -> str:
        return model.get_scout_key_name()

    def to_searchable_array(self, instance: SearchableMixin) -> dict[str, Any]:
        return instance.to_searchable_array()

    def chunk_records(
        self, model: type[SearchableMixin], *, chunk_size: int
    ) -> Iterator[list[SearchableMixin]]:
        pk_attr = getattr(model, _primary_key_attr(model))
        with self._session_factory() as session:
            records = iter(
                session.scalars(select(model).order_by(pk_attr)).yield_per(chunk_size)
            )
            while batch := list(itertools.islice(records, chunk_size)):
                yield batch

    def fetch_by_ids(
        self, model: type[SearchableMixin], ids: Sequence[Any]
    ) -> list[SearchableMixin]:
        pk_attr = getattr(model, _primary_key_attr(model))
        with self._session_factory() as session:
            return list(session.scalars(select(model).where(pk_attr.in_(list(ids)))))

    def is_soft_deleted(self, instance: SearchableMixin) -> bool:
        field = getattr(type(instance), "soft_delete_field", None)
        if field is None:
            return False
        return getattr(instance, field) is not None

    def soft_delete_enabled(self, model: type[SearchableMixin]) -> bool:
        return getattr(model, "soft_delete_field", None) is not None

    # -- query-building surface, used only by the database engine. -------

    def query_all(self, model: type[SearchableMixin]) -> Select[Any]:
        return select(model)

    def apply_search_term(
        self, query: Select[Any], model: type[SearchableMixin], term: str
    ) -> Select[Any]:
        if not term:
            return query
        strategies = get_column_strategies(model.to_searchable_array)
        columns = self._searchable_columns(model, strategies)
        if not columns:
            return query.where(false())
        boundary = _WORD_BOUNDARY_BY_DIALECT.get(
            self._dialect_name(), _DEFAULT_WORD_BOUNDARY
        )
        conditions = [
            self._column_condition(
                model, column, strategies.get(column), term, boundary
            )
            for column in columns
        ]
        return query.where(or_(*conditions))

    def _dialect_name(self) -> str:
        with self._session_factory() as session:
            return session.get_bind().dialect.name

    def _searchable_columns(
        self, model: type[SearchableMixin], strategies: dict[str, SearchStrategy]
    ) -> list[str]:
        mapper = cast("Mapper[Any]", inspect(model))
        auto_detected = {
            attr.key
            for attr in mapper.column_attrs
            if isinstance(attr.columns[0].type, (String, Text))
        }
        return sorted(auto_detected | set(strategies))

    def _column_condition(
        self,
        model: type[SearchableMixin],
        column: str,
        strategy: SearchStrategy | None,
        term: str,
        boundary: str,
    ) -> Any:
        attr = getattr(model, column)
        if strategy is SearchStrategy.PREFIX:
            return attr.ilike(f"{term}%")
        if strategy is SearchStrategy.FULL_TEXT:
            return attr.regexp_match(rf"(?i){boundary}{re.escape(term)}{boundary}")
        return attr.ilike(f"%{term}%")

    def apply_where(self, query: Select[Any], field: str, value: Any) -> Select[Any]:
        attr = getattr(_entity(query), field)
        return query.where(attr == value)

    def apply_where_in(
        self, query: Select[Any], field: str, values: Sequence[Any]
    ) -> Select[Any]:
        attr = getattr(_entity(query), field)
        return query.where(attr.in_(list(values)))

    def apply_where_not_in(
        self, query: Select[Any], field: str, values: Sequence[Any]
    ) -> Select[Any]:
        attr = getattr(_entity(query), field)
        return query.where(attr.not_in(list(values)))

    def apply_trashed_filter(
        self,
        query: Select[Any],
        model: type[SearchableMixin],
        *,
        with_trashed: bool,
        only_trashed: bool,
    ) -> Select[Any]:
        field = getattr(model, "soft_delete_field", None)
        if field is None:
            return query
        attr = getattr(model, field)
        if only_trashed:
            return query.where(attr.is_not(None))
        if with_trashed:
            return query
        return query.where(attr.is_(None))

    def execute_query(self, query: Select[Any]) -> list[SearchableMixin]:
        with self._session_factory() as session:
            return list(session.scalars(query))

    def count_query(self, query: Select[Any]) -> int:
        with self._session_factory() as session:
            return (
                session.scalar(select(func.count()).select_from(query.subquery())) or 0
            )

    def paginate_query(
        self, query: Select[Any], *, per_page: int, page: int
    ) -> list[SearchableMixin]:
        start = (page - 1) * per_page
        with self._session_factory() as session:
            return list(session.scalars(query.offset(start).limit(per_page)))
