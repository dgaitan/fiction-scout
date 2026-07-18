"""Proves `MeilisearchEngine` works end-to-end against the real Django adapter.

`tests/test_meilisearch/test_meilisearch_engine.py` already proves this
engine's own logic is correct against `tests.support.FakeAdapter`, and
`tests/test_meilisearch/test_meilisearch_live.py` proves it against a real
Meilisearch server using that same fake adapter. Neither exercises the real
`DjangoAdapter` — in particular, whether a real Django model's integer
`AutoField` primary key threads correctly through `add_documents`'s
`primary_key` argument and back through a `pk__in` query, given Meilisearch
(unlike Algolia) echoes the primary key back at its original type rather
than coercing it to a string. These tests exercise the full stack (Django
signals -> `SearchableMixin` -> `orchestration` -> `MeilisearchEngine` ->
the fake Meilisearch wire boundary, and back) to prove that holds.
"""

from __future__ import annotations

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from fiction_scout.sync.context import without_syncing_to_search
from tests.django_app.models import Article
from tests.support import FakeMeilisearchClient

pytestmark = [pytest.mark.django, pytest.mark.django_db, pytest.mark.meilisearch]


def test_given_article_saved_then_add_documents_called_with_real_pk_as_primary_key(
    meilisearch_client: FakeMeilisearchClient,
) -> None:
    article = Article.objects.create(title="Star Wars", body="A New Hope")

    assert len(meilisearch_client.added) == 1
    index_name, documents, primary_key = meilisearch_client.added[0]
    assert index_name == Article._meta.db_table
    assert primary_key == "id"
    assert documents == [{"id": article.pk, "title": "Star Wars", "body": "A New Hope"}]


def test_given_article_deleted_then_delete_documents_called_with_real_pk(
    meilisearch_client: FakeMeilisearchClient,
) -> None:
    article = Article.objects.create(title="Star Wars", body="A New Hope")
    meilisearch_client.added.clear()

    article_id = article.pk
    article.delete()

    assert meilisearch_client.deleted == [(Article._meta.db_table, [article_id])]


def test_given_native_int_hits_when_search_get_called_then_returns_articles(
    meilisearch_client: FakeMeilisearchClient,
) -> None:
    matching = Article.objects.create(title="Star Wars", body="A New Hope")
    Article.objects.create(title="Star Trek", body="The Wrath of Khan")
    meilisearch_client.added.clear()
    meilisearch_client.set_search_response(
        hits=[{"id": matching.pk, "title": "Star Wars", "body": "A New Hope"}],
        estimated_total_hits=1,
    )

    # Proves Django's ORM correctly filters on Meilisearch's own hit ids —
    # already native ints here, unlike Algolia's always-string `objectID` —
    # in a single `pk__in` query, the exact round-trip `fetch_matched_models`
    # relies on regardless of which type the search backend hands back.
    with CaptureQueriesContext(connection) as captured:
        results = Article.search("star wars").get()

    assert results == [matching]
    assert len(captured) == 1


def test_given_soft_deleted_article_saved_then_removed_from_meilisearch_not_updated(
    meilisearch_client: FakeMeilisearchClient,
) -> None:
    article = Article.objects.create(title="Star Wars", body="A New Hope")
    meilisearch_client.added.clear()

    article.deleted_at = timezone.now()
    article.save()

    assert meilisearch_client.added == []
    assert meilisearch_client.deleted == [(Article._meta.db_table, [article.pk])]


def test_given_without_syncing_when_article_saved_then_meilisearch_not_touched(
    meilisearch_client: FakeMeilisearchClient,
) -> None:
    with without_syncing_to_search():
        Article.objects.create(title="Star Wars", body="A New Hope")

    assert meilisearch_client.added == []
    assert meilisearch_client.deleted == []
