"""Proves the SQLAlchemy and Django mixins expose the same public surface.

Needs both ORM extras together, and Django settings configured (defining any
`django.db.models.Model` subclass — which `SearchableMixin` is — raises
`ImproperlyConfigured` without them), so this file is collected only when
both are available together — see `tests/conftest.py`'s dedicated guard,
mirroring the existing Django+Algolia/Meilisearch integration test guards.
"""

from __future__ import annotations

import inspect

import pytest

from fiction_scout.adapters.django.mixin import SearchableMixin as DjangoSearchableMixin
from fiction_scout.adapters.sqlalchemy.mixin import SearchableMixin as SQLAlchemyMixin

pytestmark = pytest.mark.sqlalchemy

_PARITY_METHODS = (
    "to_searchable_array",
    "searchable_as",
    "get_scout_key",
    "get_scout_key_name",
    "search",
    "searchable",
    "unsearchable",
    "should_be_searchable",
    "get_scout_adapter",
    "get_scout_engine_manager",
    "get_scout_dispatcher",
)


@pytest.mark.parametrize("name", _PARITY_METHODS)
def test_given_both_mixins_when_method_compared_then_signature_matches(
    name: str,
) -> None:
    sqlalchemy_method = getattr(SQLAlchemyMixin, name)
    django_method = getattr(DjangoSearchableMixin, name)

    assert inspect.signature(sqlalchemy_method) == inspect.signature(django_method)
