from __future__ import annotations

import itertools
import re
from collections.abc import Iterator, Sequence
from typing import TYPE_CHECKING, Any

from django.db.models import CharField, EmailField, Q, SlugField, TextField, URLField

from fiction_scout.strategies import SearchStrategy, get_column_strategies

if TYPE_CHECKING:
    from django.db.models import QuerySet

    from fiction_scout.adapters.django.mixin import SearchableMixin

_TEXT_FIELD_TYPES = (CharField, TextField, SlugField, EmailField, URLField)


class DjangoAdapter:
    """Implements `SearchableAdapter` for Django models.

    Delegates model-specific behavior (`searchable_as`, `get_scout_key`,
    `to_searchable_array`) to the methods `SearchableMixin` puts on the
    model itself.
    """

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
        queryset = model._default_manager.order_by(model._meta.pk.attname)
        records = queryset.iterator(chunk_size=chunk_size)
        while batch := list(itertools.islice(records, chunk_size)):
            yield batch

    def fetch_by_ids(
        self, model: type[SearchableMixin], ids: Sequence[Any]
    ) -> list[SearchableMixin]:
        return list(model._default_manager.filter(pk__in=list(ids)))

    def is_soft_deleted(self, instance: SearchableMixin) -> bool:
        field = getattr(type(instance), "soft_delete_field", None)
        if field is None:
            return False
        return getattr(instance, field) is not None

    def soft_delete_enabled(self, model: type[SearchableMixin]) -> bool:
        return getattr(model, "soft_delete_field", None) is not None

    # -- query-building surface, used only by the database engine. -------

    def query_all(self, model: type[SearchableMixin]) -> QuerySet[Any]:
        return model._default_manager.all()

    def apply_search_term(
        self, query: QuerySet[Any], model: type[SearchableMixin], term: str
    ) -> QuerySet[Any]:
        if not term:
            return query
        strategies = get_column_strategies(model.to_searchable_array)
        columns = self._searchable_columns(model, strategies)
        if not columns:
            return query.none()
        condition = Q()
        for column in columns:
            condition |= self._column_lookup(column, strategies.get(column), term)
        return query.filter(condition)

    def _searchable_columns(
        self, model: type[SearchableMixin], strategies: dict[str, SearchStrategy]
    ) -> list[str]:
        auto_detected = {
            f.name for f in model._meta.get_fields() if isinstance(f, _TEXT_FIELD_TYPES)
        }
        return sorted(auto_detected | set(strategies))

    def _column_lookup(
        self, column: str, strategy: SearchStrategy | None, term: str
    ) -> Q:
        if strategy is SearchStrategy.PREFIX:
            return Q(**{f"{column}__istartswith": term})
        if strategy is SearchStrategy.FULL_TEXT:
            # Whole-word regex match rather than a database-specific
            # full-text index, so this adapter behaves identically on
            # SQLite (tests) and Postgres alike. Swap in
            # django.contrib.postgres.search.SearchVector for a real index.
            return Q(**{f"{column}__iregex": rf"\b{re.escape(term)}\b"})
        return Q(**{f"{column}__icontains": term})

    def apply_where(
        self, query: QuerySet[Any], field: str, value: Any
    ) -> QuerySet[Any]:
        return query.filter(**{field: value})

    def apply_where_in(
        self, query: QuerySet[Any], field: str, values: Sequence[Any]
    ) -> QuerySet[Any]:
        return query.filter(**{f"{field}__in": list(values)})

    def apply_where_not_in(
        self, query: QuerySet[Any], field: str, values: Sequence[Any]
    ) -> QuerySet[Any]:
        return query.exclude(**{f"{field}__in": list(values)})

    def apply_trashed_filter(
        self,
        query: QuerySet[Any],
        model: type[SearchableMixin],
        *,
        with_trashed: bool,
        only_trashed: bool,
    ) -> QuerySet[Any]:
        field = getattr(model, "soft_delete_field", None)
        if field is None:
            return query
        if only_trashed:
            return query.filter(**{f"{field}__isnull": False})
        if with_trashed:
            return query
        return query.filter(**{f"{field}__isnull": True})

    def execute_query(self, query: QuerySet[Any]) -> list[SearchableMixin]:
        return list(query)

    def count_query(self, query: QuerySet[Any]) -> int:
        return query.count()

    def paginate_query(
        self, query: QuerySet[Any], *, per_page: int, page: int
    ) -> list[SearchableMixin]:
        start = (page - 1) * per_page
        return list(query[start : start + per_page])
