from __future__ import annotations

import importlib.util
import os

import pytest

from tests.support import Article, FakeAdapter

# `collect_ignore` runs before any `-m` marker filtering, so it's the actual
# mechanism that lets a bare `pytest`/`uv run pytest` (no DJANGO_SETTINGS_MODULE,
# no marker selection) work with zero ORM setup: `tests/django_app/models.py`
# and `tests/sqlalchemy_app`'s future models import their ORM at module level,
# which breaks collection outright if the ORM isn't configured — a marker alone
# can't prevent that, since pytest still has to import the module to see its
# markers. Set DJANGO_SETTINGS_MODULE (as nox's test_django session does) to
# opt back in.
collect_ignore: list[str] = []
if not os.environ.get("DJANGO_SETTINGS_MODULE"):
    collect_ignore += ["django_app", "test_django", "cli"]
if importlib.util.find_spec("sqlalchemy") is None:
    collect_ignore += ["sqlalchemy_app", "test_sqlalchemy"]
if importlib.util.find_spec("celery") is None:
    collect_ignore += ["test_celery"]
if importlib.util.find_spec("algoliasearch") is None:
    collect_ignore += ["test_algolia"]
    # The Django+Algolia integration test needs both extras together; guard
    # it independently of the "test_django" bulk entry above, which only
    # tracks DJANGO_SETTINGS_MODULE, not algoliasearch's presence.
    collect_ignore += ["test_django/test_algolia_integration.py"]
if importlib.util.find_spec("meilisearch") is None:
    collect_ignore += ["test_meilisearch"]
    # Same reasoning as the Django+Algolia guard above: this one test module
    # needs both `django` and `meilisearch` together to even collect.
    collect_ignore += ["test_django/test_meilisearch_integration.py"]
if (
    not os.environ.get("DJANGO_SETTINGS_MODULE")
    or importlib.util.find_spec("sqlalchemy") is None
):
    # Same "needs both extras together" reasoning as the Django+Algolia guard
    # above: defining any `django.db.models.Model` subclass (the Django
    # `SearchableMixin` this file compares against) requires configured
    # Django settings, not just the package installed — `nox -s
    # test_sqlalchemy` installs sqlalchemy without django at all, and even a
    # plain `pytest` in a dev venv with both extras installed but no
    # DJANGO_SETTINGS_MODULE set would otherwise fail at collection.
    collect_ignore += ["test_sqlalchemy/test_mixin_parity.py"]


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
