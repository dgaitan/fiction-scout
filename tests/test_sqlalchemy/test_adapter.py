from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import Engine, event
from sqlalchemy.orm import Session, sessionmaker

from fiction_scout.adapters.sqlalchemy import runtime
from fiction_scout.adapters.sqlalchemy.adapter import SQLAlchemyAdapter
from tests.sqlalchemy_app.models import Article

pytestmark = pytest.mark.sqlalchemy


@pytest.fixture
def adapter(session_factory: sessionmaker[Session]) -> SQLAlchemyAdapter:
    return SQLAlchemyAdapter(session_factory)


def _make_articles(session_factory: sessionmaker[Session], n: int) -> None:
    with session_factory() as session:
        for i in range(1, n + 1):
            session.add(Article(title=f"Title {i}", body=f"Body {i}"))
        session.commit()


def test_given_seven_rows_when_chunk_records_size_three_then_yields_three_batches(
    adapter: SQLAlchemyAdapter, session_factory: sessionmaker[Session]
) -> None:
    _make_articles(session_factory, 7)

    batches = list(adapter.chunk_records(Article, chunk_size=3))

    assert [len(batch) for batch in batches] == [3, 3, 1]
    assert sum(len(batch) for batch in batches) == 7


def test_given_ids_list_when_fetch_by_ids_called_then_issues_exactly_one_query(
    adapter: SQLAlchemyAdapter, session_factory: sessionmaker[Session], engine: Engine
) -> None:
    _make_articles(session_factory, 3)
    with session_factory() as session:
        ids = [row.id for row in session.query(Article).all()]

    statements: list[str] = []

    def _track(*args: object, **kwargs: object) -> None:
        statements.append("query")

    event.listen(engine, "before_cursor_execute", _track)
    try:
        results = adapter.fetch_by_ids(Article, ids)
    finally:
        event.remove(engine, "before_cursor_execute", _track)

    assert len(statements) == 1
    assert {a.id for a in results} == set(ids)


def test_given_like_strategy_when_term_applied_then_matches_substring_case_insensitive(
    adapter: SQLAlchemyAdapter, session_factory: sessionmaker[Session]
) -> None:
    with session_factory() as session:
        session.add(Article(title="Star Wars", body="A New Hope"))
        session.add(Article(title="Star Trek", body="The Wrath of Khan"))
        session.commit()

    query = adapter.apply_search_term(adapter.query_all(Article), Article, "new hope")

    assert [a.title for a in adapter.execute_query(query)] == ["Star Wars"]


def test_given_prefix_strategy_on_title_when_term_matches_middle_only_then_no_match(
    adapter: SQLAlchemyAdapter, session_factory: sessionmaker[Session]
) -> None:
    with session_factory() as session:
        session.add(Article(title="Star Wars", body="prologue"))
        session.commit()

    query = adapter.apply_search_term(adapter.query_all(Article), Article, "Wars")

    assert adapter.execute_query(query) == []


def test_given_prefix_strategy_on_title_when_term_matches_prefix_then_matched(
    adapter: SQLAlchemyAdapter, session_factory: sessionmaker[Session]
) -> None:
    with session_factory() as session:
        session.add(Article(title="Star Wars", body="prologue"))
        session.commit()

    query = adapter.apply_search_term(adapter.query_all(Article), Article, "Star")

    assert [a.title for a in adapter.execute_query(query)] == ["Star Wars"]


def test_given_full_text_strategy_when_term_matches_substring_not_word_then_no_match(
    adapter: SQLAlchemyAdapter, session_factory: sessionmaker[Session]
) -> None:
    with session_factory() as session:
        session.add(Article(title="Report", body="Stardust settled"))
        session.commit()

    query = adapter.apply_search_term(adapter.query_all(Article), Article, "star")

    assert adapter.execute_query(query) == []


def test_given_full_text_strategy_on_body_when_term_matches_whole_word_then_matched(
    adapter: SQLAlchemyAdapter, session_factory: sessionmaker[Session]
) -> None:
    with session_factory() as session:
        session.add(Article(title="Report", body="the star shone"))
        session.commit()

    query = adapter.apply_search_term(adapter.query_all(Article), Article, "star")

    assert [a.title for a in adapter.execute_query(query)] == ["Report"]


def test_given_no_trashed_flags_when_apply_trashed_filter_called_then_excludes_deleted(
    adapter: SQLAlchemyAdapter, session_factory: sessionmaker[Session]
) -> None:
    with session_factory() as session:
        live = Article(title="Live", body="live body")
        gone = Article(
            title="Gone", body="gone body", deleted_at=datetime.now(timezone.utc)
        )
        session.add_all([live, gone])
        session.commit()
        live_id = live.id

    query = adapter.apply_trashed_filter(
        adapter.query_all(Article), Article, with_trashed=False, only_trashed=False
    )

    assert [a.id for a in adapter.execute_query(query)] == [live_id]


def test_given_with_trashed_true_when_apply_trashed_filter_called_then_includes_deleted(
    adapter: SQLAlchemyAdapter, session_factory: sessionmaker[Session]
) -> None:
    with session_factory() as session:
        session.add(Article(title="Live", body="live body"))
        session.add(
            Article(
                title="Gone", body="gone body", deleted_at=datetime.now(timezone.utc)
            )
        )
        session.commit()

    query = adapter.apply_trashed_filter(
        adapter.query_all(Article), Article, with_trashed=True, only_trashed=False
    )

    assert len(adapter.execute_query(query)) == 2


def test_given_only_trashed_true_when_trashed_filter_called_then_returns_only_deleted(
    adapter: SQLAlchemyAdapter, session_factory: sessionmaker[Session]
) -> None:
    with session_factory() as session:
        session.add(Article(title="Live", body="live body"))
        gone = Article(
            title="Gone", body="gone body", deleted_at=datetime.now(timezone.utc)
        )
        session.add(gone)
        session.commit()
        gone_id = gone.id

    query = adapter.apply_trashed_filter(
        adapter.query_all(Article), Article, with_trashed=False, only_trashed=True
    )

    assert [a.id for a in adapter.execute_query(query)] == [gone_id]


def test_given_database_driver_when_search_get_called_then_returns_instances(
    session_factory: sessionmaker[Session],
) -> None:
    runtime.configure(session_factory=session_factory)
    with session_factory() as session:
        session.add(Article(title="Star Wars", body="A New Hope"))
        session.commit()

    results = Article.search("Star").get()

    assert results and all(isinstance(item, Article) for item in results)
