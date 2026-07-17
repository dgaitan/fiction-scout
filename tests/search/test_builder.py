from __future__ import annotations

from fiction_scout.engines.collection import CollectionEngine
from fiction_scout.search.builder import Builder
from tests.support import Article, FakeAdapter


def _builder(adapter: FakeAdapter) -> Builder:
    return Builder(Article, "star", engine=CollectionEngine(), adapter=adapter)


def test_chainable_methods_return_the_builder(adapter: FakeAdapter) -> None:
    builder = _builder(adapter)
    assert builder.where("id", 1) is builder
    assert builder.where_in("id", [1]) is builder
    assert builder.where_not_in("id", [2]) is builder
    assert builder.within("custom_index") is builder
    assert builder.query(lambda q: q) is builder
    assert builder.with_trashed() is builder
    assert builder.only_trashed() is builder


def test_defaults_are_empty(adapter: FakeAdapter) -> None:
    builder = _builder(adapter)
    assert builder.wheres == {}
    assert builder.where_ins == {}
    assert builder.where_not_ins == {}
    assert builder.index is None
    assert builder.query_callback is None
    assert builder.with_trashed_ is False
    assert builder.only_trashed_ is False


def test_with_trashed_and_only_trashed_are_mutually_exclusive(adapter: FakeAdapter) -> None:
    builder = _builder(adapter)
    builder.with_trashed()
    assert (builder.with_trashed_, builder.only_trashed_) == (True, False)
    builder.only_trashed()
    assert (builder.with_trashed_, builder.only_trashed_) == (False, True)
    builder.with_trashed()
    assert (builder.with_trashed_, builder.only_trashed_) == (True, False)


def test_raw_delegates_to_engine_search(adapter: FakeAdapter) -> None:
    builder = _builder(adapter)
    assert builder.raw() == builder.engine.search(builder)


def test_get_delegates_to_engine_get(adapter: FakeAdapter) -> None:
    builder = _builder(adapter)
    assert [a.id for a in builder.get()] == [1, 2]
