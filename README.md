# fiction-scout

A simple, driver-based solution for adding full-text search to your models —
for Django, Flask, or any other Python project.

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

Python has no single dominant ORM, so fiction-scout is built around one
seam: the `SearchableAdapter` protocol in
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

Unlike Django, SQLAlchemy has no settings-style implicit registry to
auto-discover a database connection from — call `runtime.configure()` once
at startup with your `sessionmaker`. This is also what wires up the
`before_commit`/`after_commit` auto-sync hooks.

```python
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from fiction_scout.adapters.sqlalchemy import runtime
from fiction_scout.adapters.sqlalchemy.mixin import SearchableMixin


class Base(DeclarativeBase):
    pass


class Post(SearchableMixin, Base):
    __tablename__ = "posts"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str]
    body: Mapped[str]


Session = sessionmaker(bind=engine)
runtime.configure(session_factory=Session)

# Saving a Post automatically syncs it to the configured search index.
with Session() as session:
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

Full documentation: [`docs/index.md`](docs/index.md). Full tutorials
building a Movies API end to end: [`docs/tutorials/`](docs/tutorials/index.md).

## Development

```bash
uv venv && source .venv/bin/activate
uv pip install -e ".[dev,django,sqlalchemy,celery]"
nox -s lint typecheck test_core test_django test_sqlalchemy
```

## License

MIT — see [`LICENSE`](LICENSE).
