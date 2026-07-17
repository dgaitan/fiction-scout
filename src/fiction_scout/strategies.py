"""Per-column search strategies for the database engine.

Mirrors Scout's `SearchUsingFullText`/`SearchUsingPrefix` PHP attributes as
Python decorators applied to a model's `to_searchable_array` method. Columns
with no decorator default to a `LIKE '%term%'` match.

    class Post(SearchableMixin, Base):
        @search_using_full_text("body")
        @search_using_prefix("id", "email")
        def to_searchable_array(self) -> dict[str, Any]:
            return {"id": self.id, "email": self.email, "body": self.body}
"""

from __future__ import annotations

import enum
from typing import Any, Callable, TypeVar

F = TypeVar("F", bound=Callable[..., dict[str, Any]])

_STRATEGY_ATTR = "_fiction_scout_column_strategies"


class SearchStrategy(enum.Enum):
    """How the database engine matches one column against the search term."""

    LIKE = "like"
    FULL_TEXT = "full_text"
    PREFIX = "prefix"


def _apply_strategy(strategy: SearchStrategy, *columns: str) -> Callable[[F], F]:
    def decorator(fn: F) -> F:
        existing: dict[str, SearchStrategy] = dict(getattr(fn, _STRATEGY_ATTR, {}))
        existing.update(dict.fromkeys(columns, strategy))
        setattr(fn, _STRATEGY_ATTR, existing)
        return fn

    return decorator


def search_using_full_text(*columns: str) -> Callable[[F], F]:
    """Decorate `to_searchable_array` to match `columns` via a full-text index.

    Before use, ensure each column has an actual full-text index defined at
    the database level — this decorator only changes which query fiction-scout
    builds, it doesn't create the index.
    """
    return _apply_strategy(SearchStrategy.FULL_TEXT, *columns)


def search_using_prefix(*columns: str) -> Callable[[F], F]:
    """Decorate `to_searchable_array` to match `columns` via `term%` prefix only."""
    return _apply_strategy(SearchStrategy.PREFIX, *columns)


def get_column_strategies(fn: Callable[..., Any]) -> dict[str, SearchStrategy]:
    """Return the column -> strategy map attached to `fn` by the decorators above."""
    return dict(getattr(fn, _STRATEGY_ATTR, {}))
