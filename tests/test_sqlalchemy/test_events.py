from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy.orm import Session, sessionmaker

from fiction_scout.sync.context import without_syncing_to_search
from tests.sqlalchemy_app.models import Article
from tests.support import SpyEngine

pytestmark = pytest.mark.sqlalchemy


def test_given_instance_added_when_session_commits_then_synced_to_engine(
    spy_engine: SpyEngine, session_factory: sessionmaker[Session]
) -> None:
    article = Article(title="Star Wars", body="A New Hope")
    with session_factory() as session:
        session.add(article)
        session.commit()

        assert spy_engine.updated_batches == [[article]]


def test_given_instance_added_when_transaction_rolled_back_then_never_sent_to_engine(
    spy_engine: SpyEngine, session_factory: sessionmaker[Session]
) -> None:
    with session_factory() as session:
        session.add(Article(title="Star Wars", body="A New Hope"))
        session.rollback()

    assert spy_engine.updated_batches == []
    assert spy_engine.deleted_batches == []


def test_given_multiple_instances_in_one_transaction_when_committed_then_batched(
    spy_engine: SpyEngine, session_factory: sessionmaker[Session]
) -> None:
    with session_factory() as session:
        articles = [
            Article(title="Star Wars", body="A New Hope"),
            Article(title="Star Trek", body="The Wrath of Khan"),
            Article(title="Report", body="Quarterly numbers"),
        ]
        session.add_all(articles)
        session.commit()

        # `before_commit`'s capture set (`{*session.new, *session.dirty}`) has
        # no guaranteed order — only that all three land in one batch, not one
        # dispatched `update()` call per instance.
        assert len(spy_engine.updated_batches) == 1
        assert set(spy_engine.updated_batches[0]) == set(articles)


def test_given_soft_delete_field_set_true_when_committed_then_removed_from_index(
    spy_engine: SpyEngine, session_factory: sessionmaker[Session]
) -> None:
    with session_factory() as session:
        article = Article(title="Star Wars", body="A New Hope")
        session.add(article)
        session.commit()

        spy_engine.updated_batches.clear()

        article.deleted_at = datetime.now(timezone.utc)
        session.commit()

        assert spy_engine.updated_batches == []
        assert spy_engine.deleted_batches == [[article]]


def test_given_without_syncing_to_search_when_session_commits_then_engine_not_touched(
    spy_engine: SpyEngine, session_factory: sessionmaker[Session]
) -> None:
    with without_syncing_to_search():
        with session_factory() as session:
            session.add(Article(title="Star Wars", body="A New Hope"))
            session.commit()

    assert spy_engine.updated_batches == []
    assert spy_engine.deleted_batches == []
