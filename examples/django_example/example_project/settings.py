"""Minimal settings for the fiction-scout Django example.

Not production settings — `SECRET_KEY` is a placeholder and the database is
a local SQLite file, on purpose, to keep this example runnable with nothing
but `pip install "fiction-scout[django]"`.
"""

from __future__ import annotations

from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = "example-only-not-for-production"
DEBUG = True
USE_TZ = True

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "fiction_scout.adapters.django",
    "example_project.blog",
]

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# `database` needs nothing else installed; switch to "algolia" or
# "meilisearch" (after `pip install "fiction-scout[algolia]"` or
# `[meilisearch]`) to try an external search index instead.
FICTION_SCOUT = {"driver": "database"}
