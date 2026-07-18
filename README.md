# fiction-scout

A simple, driver-based solution for adding full-text search to your models —
for Django, Flask, or any other Python project. Inspired by
[Laravel Scout](https://laravel.com/docs/master/scout)'s methodlogy.

Add the `Searchable` mixin to a model and fiction-scout keeps your search
index in sync with it automatically, using each ORM's native change-tracking
mechanism (Django signals, SQLAlchemy session events) — no polling, no manual
bookkeeping.

## Status

Early development (v1, pre-release). Core engine, Database/Collection
drivers, Django + SQLAlchemy adapters, and the CLI are implemented. See
[`ROADMAP.md`](ROADMAP.md) for what's shipped vs. deliberately deferred
(third-party search engines, async support).

## Why

Python has no single dominant ORM the way Laravel has Eloquent, so
fiction-scout is built around one seam: the `SearchableAdapter` protocol in
`fiction_scout.protocols`. Every engine, the search `Builder`, and the CLI
talk only to that protocol — never directly to Django or SQLAlchemy. Two
adapters ship today (Django, SQLAlchemy); adding a third doesn't require
touching core code.

## Installation

```bash
pip install "fiction-scout[django]"      # Django projects
pip install "fiction-scout[sqlalchemy]"  # SQLAlchemy / Flask-SQLAlchemy projects
pip install "fiction-scout[celery]"      # optional: background indexing via Celery
```

## Quickstart (SQLAlchemy)

```python
from fiction_scout.adapters.sqlalchemy import SearchableMixin
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Post(Base, SearchableMixin):
    __tablename__ = "posts"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str]
    body: Mapped[str]


# Saving a Post automatically syncs it to the configured search index.
post = Post(title="Star Trek II", body="The Wrath of Khan")
session.add(post)
session.commit()

results = Post.search("Star Trek").get()
```

## Quickstart (Django)

```python
# settings.py
INSTALLED_APPS = [..., "fiction_scout.adapters.django"]
FICTION_SCOUT = {"driver": "database"}
```

```python
# models.py
from django.db import models
from fiction_scout.adapters.django.mixin import SearchableMixin


class Post(SearchableMixin, models.Model):
    title = models.CharField(max_length=255)
    body = models.TextField()


results = Post.search("Star Trek").get()
```

Full documentation: [`docs/index.md`](docs/index.md).

## Development

```bash
uv venv && source .venv/bin/activate
uv pip install -e ".[dev,django,sqlalchemy,celery]"
nox -s lint typecheck test_core test_django test_sqlalchemy
```

## License

MIT — see [`LICENSE`](LICENSE).
