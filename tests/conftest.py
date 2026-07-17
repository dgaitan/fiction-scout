from __future__ import annotations

import pytest

from tests.support import Article, FakeAdapter


@pytest.fixture
def articles() -> list[Article]:
    return [
        Article(id=1, title="Star Trek II", body="The Wrath of Khan"),
        Article(id=2, title="Star Wars", body="A New Hope"),
        Article(
            id=3, title="Archived Article", body="Old content", deleted_at="2020-01-01"
        ),
    ]


@pytest.fixture
def adapter(articles: list[Article]) -> FakeAdapter:
    return FakeAdapter(articles)
