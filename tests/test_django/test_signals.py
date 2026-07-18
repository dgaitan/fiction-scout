from __future__ import annotations

import pytest
from django.utils import timezone

from fiction_scout.sync.context import without_syncing_to_search
from tests.django_app.models import Article
from tests.support import SpyEngine

pytestmark = [pytest.mark.django, pytest.mark.django_db]


def test_given_searchable_model_when_saved_then_post_save_syncs_to_configured_engine(
    spy_engine: SpyEngine,
) -> None:
    article = Article.objects.create(title="Star Wars", body="A New Hope")

    assert spy_engine.updated_batches == [[article]]


def test_given_searchable_model_when_deleted_then_post_delete_removes_from_index(
    spy_engine: SpyEngine,
) -> None:
    article = Article.objects.create(title="Star Wars", body="A New Hope")
    spy_engine.updated_batches.clear()

    article.delete()

    assert spy_engine.deleted_batches == [[article]]


def test_given_soft_delete_field_set_true_on_save_then_removed_from_index_not_updated(
    spy_engine: SpyEngine,
) -> None:
    article = Article.objects.create(title="Star Wars", body="A New Hope")
    spy_engine.updated_batches.clear()

    article.deleted_at = timezone.now()
    article.save()

    assert spy_engine.updated_batches == []
    assert spy_engine.deleted_batches == [[article]]


def test_given_without_syncing_to_search_when_model_saved_then_engine_not_touched(
    spy_engine: SpyEngine,
) -> None:
    with without_syncing_to_search():
        Article.objects.create(title="Star Wars", body="A New Hope")

    assert spy_engine.updated_batches == []
    assert spy_engine.deleted_batches == []
