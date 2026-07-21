from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from sqlalchemy import DateTime, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from fiction_scout.adapters.sqlalchemy.mixin import SearchableMixin
from fiction_scout.strategies import search_using_full_text, search_using_prefix


class Base(DeclarativeBase):
    pass


class Article(SearchableMixin, Base):
    __tablename__ = "article"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text())
    # `Optional[...]`, not `datetime | None`: SQLAlchemy's declarative mapping
    # resolves `Mapped[...]` annotations at class-definition time via
    # `typing.get_type_hints()`, which re-evaluates the postponed-annotation
    # string even under `from __future__ import annotations` — PEP 604's
    # `X | None` syntax isn't a valid runtime expression before Python 3.10,
    # and this project's test matrix includes 3.9.
    deleted_at: Mapped[Optional[datetime]] = mapped_column(  # noqa: UP045
        DateTime(), nullable=True
    )

    soft_delete_field = "deleted_at"

    def __str__(self) -> str:
        return self.title

    @search_using_prefix("title")
    @search_using_full_text("body")
    def to_searchable_array(self) -> dict[str, Any]:
        return {"id": self.id, "title": self.title, "body": self.body}
