from __future__ import annotations

from typing import Any

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from fiction_scout.adapters.django.adapter import DjangoAdapter
from tests.django_app.models import Article

pytestmark = [pytest.mark.django, pytest.mark.django_db]


@pytest.fixture
def adapter() -> DjangoAdapter:
    return DjangoAdapter()


def _make_articles(n: int) -> None:
    for i in range(1, n + 1):
        Article.objects.create(title=f"Title {i}", body=f"Body {i}")


def test_given_seven_rows_when_chunk_records_size_three_then_yields_three_batches(
    adapter: DjangoAdapter,
) -> None:
    _make_articles(7)

    batches = list(adapter.chunk_records(Article, chunk_size=3))

    assert [len(batch) for batch in batches] == [3, 3, 1]
    assert sum(len(batch) for batch in batches) == 7


def test_given_ids_list_when_fetch_by_ids_called_then_issues_exactly_one_query(
    adapter: DjangoAdapter,
) -> None:
    _make_articles(3)
    ids = list(Article.objects.values_list("id", flat=True))

    with CaptureQueriesContext(connection) as captured:
        results = adapter.fetch_by_ids(Article, ids)

    assert len(captured) == 1
    assert {a.id for a in results} == set(ids)


def test_given_like_strategy_when_term_applied_then_matches_substring_case_insensitive(
    adapter: DjangoAdapter,
) -> None:
    Article.objects.create(title="Star Wars", body="A New Hope")
    Article.objects.create(title="Star Trek", body="The Wrath of Khan")

    query = adapter.apply_search_term(adapter.query_all(Article), Article, "new hope")

    assert [a.title for a in query] == ["Star Wars"]


def test_given_prefix_strategy_on_title_when_term_matches_middle_only_then_no_match(
    adapter: DjangoAdapter,
) -> None:
    Article.objects.create(title="Star Wars", body="prologue")

    query = adapter.apply_search_term(adapter.query_all(Article), Article, "Wars")

    assert list(query) == []


def test_given_prefix_strategy_on_title_when_term_matches_prefix_then_matched(
    adapter: DjangoAdapter,
) -> None:
    Article.objects.create(title="Star Wars", body="prologue")

    query = adapter.apply_search_term(adapter.query_all(Article), Article, "Star")

    assert [a.title for a in query] == ["Star Wars"]


def test_given_full_text_strategy_when_term_matches_substring_not_word_then_no_match(
    adapter: DjangoAdapter,
) -> None:
    Article.objects.create(title="Report", body="Stardust settled")

    query = adapter.apply_search_term(adapter.query_all(Article), Article, "star")

    assert list(query) == []


def test_given_full_text_strategy_on_body_when_term_matches_whole_word_then_matched(
    adapter: DjangoAdapter,
) -> None:
    Article.objects.create(title="Report", body="the star shone")

    query = adapter.apply_search_term(adapter.query_all(Article), Article, "star")

    assert [a.title for a in query] == ["Report"]


def test_given_no_trashed_flags_when_apply_trashed_filter_called_then_excludes_deleted(
    adapter: DjangoAdapter,
) -> None:
    live = Article.objects.create(title="Live", body="live body")
    Article.objects.create(title="Gone", body="gone body", deleted_at=timezone.now())

    query = adapter.apply_trashed_filter(
        adapter.query_all(Article), Article, with_trashed=False, only_trashed=False
    )

    assert [a.id for a in query] == [live.id]


def test_given_with_trashed_true_when_apply_trashed_filter_called_then_includes_deleted(
    adapter: DjangoAdapter,
) -> None:
    Article.objects.create(title="Live", body="live body")
    Article.objects.create(title="Gone", body="gone body", deleted_at=timezone.now())

    query = adapter.apply_trashed_filter(
        adapter.query_all(Article), Article, with_trashed=True, only_trashed=False
    )

    assert query.count() == 2


def test_given_only_trashed_true_when_trashed_filter_called_then_returns_only_deleted(
    adapter: DjangoAdapter,
) -> None:
    Article.objects.create(title="Live", body="live body")
    gone = Article.objects.create(
        title="Gone", body="gone body", deleted_at=timezone.now()
    )

    query = adapter.apply_trashed_filter(
        adapter.query_all(Article), Article, with_trashed=False, only_trashed=True
    )

    assert [a.id for a in query] == [gone.id]


def test_given_database_driver_when_search_get_called_then_returns_instances() -> None:
    Article.objects.create(title="Star Wars", body="A New Hope")

    results = Article.search("Star").get()

    assert results and all(isinstance(item, Article) for item in results)


def _iregex_pattern(query: Any) -> str:
    or_node = query.query.where.children[0]
    lookup = next(lu for lu in or_node.children if lu.lookup_name == "iregex")
    return lookup.rhs


def test_given_postgresql_vendor_when_full_text_regex_built_then_uses_postgres_boundary(
    adapter: DjangoAdapter, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(connection, "vendor", "postgresql")

    query = adapter.apply_search_term(adapter.query_all(Article), Article, "star")

    assert _iregex_pattern(query) == r"\ystar\y"


def test_given_sqlite_vendor_when_full_text_regex_built_then_uses_perl_word_boundary(
    adapter: DjangoAdapter,
) -> None:
    query = adapter.apply_search_term(adapter.query_all(Article), Article, "star")

    assert _iregex_pattern(query) == r"\bstar\b"
