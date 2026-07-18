"""Proves `AlgoliaEngine` works end-to-end against the real Django adapter.

`tests/test_algolia/test_algolia_engine.py` already proves `AlgoliaEngine`'s
own logic is correct against `tests.support.FakeAdapter`. What that suite
can't prove is that the *real* `DjangoAdapter` produces data `AlgoliaEngine`
can actually round-trip — in particular, Algolia's `objectID` is always a
string while a Django model's primary key is a real `int` (`AutoField`).
These tests exercise the full stack (Django signals -> `SearchableMixin` ->
`orchestration` -> `AlgoliaEngine` -> the fake Algolia wire boundary, and
back) to prove that round-trip holds, not just assume it does because the
protocol types line up on paper.
"""

from __future__ import annotations

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from fiction_scout.sync.context import without_syncing_to_search
from tests.django_app.models import Article
from tests.support import AlgoliaHit, FakeAlgoliaClient

pytestmark = [pytest.mark.django, pytest.mark.django_db, pytest.mark.algolia]


def test_given_article_saved_then_save_objects_called_with_real_pk_as_object_id(
    algolia_client: FakeAlgoliaClient,
) -> None:
    article = Article.objects.create(title="Star Wars", body="A New Hope")

    assert len(algolia_client.saved) == 1
    index_name, objects = algolia_client.saved[0]
    assert index_name == Article._meta.db_table
    assert objects == [
        {
            "id": article.pk,
            "title": "Star Wars",
            "body": "A New Hope",
            "objectID": str(article.pk),
        }
    ]


def test_given_article_deleted_then_delete_objects_called_with_real_pk_as_string(
    algolia_client: FakeAlgoliaClient,
) -> None:
    article = Article.objects.create(title="Star Wars", body="A New Hope")
    algolia_client.saved.clear()

    article_id = article.pk
    article.delete()

    assert algolia_client.deleted == [(Article._meta.db_table, [str(article_id)])]


def test_given_string_object_ids_when_search_get_called_then_returns_articles(
    algolia_client: FakeAlgoliaClient,
) -> None:
    matching = Article.objects.create(title="Star Wars", body="A New Hope")
    Article.objects.create(title="Star Trek", body="The Wrath of Khan")
    algolia_client.saved.clear()
    algolia_client.set_search_response(
        hits=[AlgoliaHit(object_id=str(matching.pk))], nb_hits=1
    )

    # Proves Django's ORM correctly coerces Algolia's string document id
    # against the integer primary key column in a single `pk__in` query —
    # the exact round-trip `fetch_matched_models` relies on.
    with CaptureQueriesContext(connection) as captured:
        results = Article.search("star wars").get()

    assert results == [matching]
    assert len(captured) == 1


def test_given_soft_deleted_article_saved_then_removed_from_algolia_not_updated(
    algolia_client: FakeAlgoliaClient,
) -> None:
    article = Article.objects.create(title="Star Wars", body="A New Hope")
    algolia_client.saved.clear()

    article.deleted_at = timezone.now()
    article.save()

    assert algolia_client.saved == []
    assert algolia_client.deleted == [(Article._meta.db_table, [str(article.pk)])]


def test_given_without_syncing_to_search_when_article_saved_then_algolia_not_touched(
    algolia_client: FakeAlgoliaClient,
) -> None:
    with without_syncing_to_search():
        Article.objects.create(title="Star Wars", body="A New Hope")

    assert algolia_client.saved == []
    assert algolia_client.deleted == []
