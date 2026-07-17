from __future__ import annotations

from fiction_scout.engines.collection import CollectionEngine
from fiction_scout.search.builder import Builder
from tests.support import Article, FakeAdapter


def test_search_matches_query_across_all_fields(adapter: FakeAdapter, articles: list[Article]) -> None:
    engine = CollectionEngine()
    builder = Builder(Article, "wrath", engine=engine, adapter=adapter)
    assert [a.id for a in engine.get(builder)] == [1]


def test_search_excludes_soft_deleted_by_default(adapter: FakeAdapter, articles: list[Article]) -> None:
    engine = CollectionEngine()
    builder = Builder(Article, "archived", engine=engine, adapter=adapter)
    assert engine.get(builder) == []


def test_with_trashed_includes_soft_deleted(adapter: FakeAdapter, articles: list[Article]) -> None:
    engine = CollectionEngine()
    builder = Builder(Article, "archived", engine=engine, adapter=adapter).with_trashed()
    assert [a.id for a in engine.get(builder)] == [3]


def test_only_trashed_returns_only_soft_deleted(adapter: FakeAdapter, articles: list[Article]) -> None:
    engine = CollectionEngine()
    builder = Builder(Article, "", engine=engine, adapter=adapter).only_trashed()
    assert [a.id for a in engine.get(builder)] == [3]


def test_where_constrains_results(adapter: FakeAdapter, articles: list[Article]) -> None:
    engine = CollectionEngine()
    builder = Builder(Article, "star", engine=engine, adapter=adapter).where("id", 2)
    assert [a.id for a in engine.get(builder)] == [2]


def test_where_in_constrains_results(adapter: FakeAdapter, articles: list[Article]) -> None:
    engine = CollectionEngine()
    builder = Builder(Article, "star", engine=engine, adapter=adapter).where_in("id", [1])
    assert [a.id for a in engine.get(builder)] == [1]


def test_where_not_in_excludes_results(adapter: FakeAdapter, articles: list[Article]) -> None:
    engine = CollectionEngine()
    builder = Builder(Article, "star", engine=engine, adapter=adapter).where_not_in("id", [1])
    assert [a.id for a in engine.get(builder)] == [2]


def test_paginate_returns_page_metadata(adapter: FakeAdapter, articles: list[Article]) -> None:
    engine = CollectionEngine()
    builder = Builder(Article, "star", engine=engine, adapter=adapter)
    page = engine.paginate(builder, per_page=1, page=1)
    assert page.total == 2
    assert len(page.items) == 1
    assert page.has_more is True


def test_map_ids_returns_scout_keys(adapter: FakeAdapter, articles: list[Article]) -> None:
    engine = CollectionEngine()
    builder = Builder(Article, "star", engine=engine, adapter=adapter)
    raw = engine.search(builder)
    assert set(engine.map_ids(raw)) == {1, 2}


def test_get_total_count(adapter: FakeAdapter, articles: list[Article]) -> None:
    engine = CollectionEngine()
    builder = Builder(Article, "star", engine=engine, adapter=adapter)
    raw = engine.search(builder)
    assert engine.get_total_count(raw) == 2


def test_update_delete_flush_are_inert_noops(adapter: FakeAdapter, articles: list[Article]) -> None:
    engine = CollectionEngine()
    # The collection engine always reads live data — these must not raise
    # and must not be expected to have any observable effect.
    engine.update(articles, adapter)
    engine.delete(articles, adapter)
    engine.flush(Article, adapter)
