from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from fiction_scout.engines.database import DatabaseEngine
from fiction_scout.search.builder import Builder
from fiction_scout.strategies import search_using_prefix
from tests.support import Article, FakeAdapter


def test_search_matches_via_like_by_default(adapter: FakeAdapter, articles: list[Article]) -> None:
    engine = DatabaseEngine()
    builder = Builder(Article, "wrath", engine=engine, adapter=adapter)
    assert [a.id for a in engine.get(builder)] == [1]


def test_where_not_in_composes_with_search_term(adapter: FakeAdapter, articles: list[Article]) -> None:
    engine = DatabaseEngine()
    builder = Builder(Article, "star", engine=engine, adapter=adapter).where_not_in("id", [2])
    assert [a.id for a in engine.get(builder)] == [1]


def test_only_trashed_filter(adapter: FakeAdapter, articles: list[Article]) -> None:
    engine = DatabaseEngine()
    builder = Builder(Article, "", engine=engine, adapter=adapter).only_trashed()
    assert [a.id for a in engine.get(builder)] == [3]


def test_with_trashed_includes_soft_deleted(adapter: FakeAdapter, articles: list[Article]) -> None:
    engine = DatabaseEngine()
    builder = Builder(Article, "", engine=engine, adapter=adapter).with_trashed()
    assert {a.id for a in engine.get(builder)} == {1, 2, 3}


def test_paginate(adapter: FakeAdapter, articles: list[Article]) -> None:
    engine = DatabaseEngine()
    builder = Builder(Article, "star", engine=engine, adapter=adapter)
    page = engine.paginate(builder, per_page=1, page=2)
    assert page.total == 2
    assert len(page.items) == 1


def test_query_callback_runs_after_other_constraints(adapter: FakeAdapter, articles: list[Article]) -> None:
    engine = DatabaseEngine()
    seen_length = {}

    def callback(query: list[Article]) -> list[Article]:
        seen_length["value"] = len(query)
        return query

    builder = Builder(Article, "star", engine=engine, adapter=adapter).query(callback)
    engine.get(builder)
    assert seen_length["value"] == 2


def test_prefix_strategy_only_matches_start_of_string() -> None:
    @dataclass
    class Doc:
        id: int
        title: str
        deleted_at: str | None = None

        @search_using_prefix("title")
        def to_searchable_array(self) -> dict[str, Any]:
            return {"id": self.id, "title": self.title}

    docs = [Doc(id=1, title="Star Trek II"), Doc(id=2, title="Second Star Trek")]
    adapter = FakeAdapter(docs)
    engine = DatabaseEngine()

    prefix_match = Builder(Doc, "Star", engine=engine, adapter=adapter)
    assert [d.id for d in engine.get(prefix_match)] == [1]

    mid_string_only = Builder(Doc, "Trek", engine=engine, adapter=adapter)
    assert engine.get(mid_string_only) == []


def test_update_delete_flush_are_inert_noops(adapter: FakeAdapter, articles: list[Article]) -> None:
    engine = DatabaseEngine()
    engine.update(articles, adapter)
    engine.delete(articles, adapter)
    engine.flush(Article, adapter)
