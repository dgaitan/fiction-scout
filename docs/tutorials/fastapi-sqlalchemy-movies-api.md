# Tutorial: Movies API with FastAPI + SQLAlchemy

The same Movies API as the [Django + Algolia tutorial](django-algolia-movies-api.md)
— list, filter by `director`/`category`, full-text search — but on FastAPI
with SQLAlchemy, using fiction-scout's built-in `database` driver instead of
an external search service. No account, no API key, nothing to sign up
for: `database` searches the same SQLite table your app already writes to,
via `LIKE`/prefix/full-text query strategies instead of a separate index.
That trade-off (zero external dependencies, but no faceted search or typo
tolerance) is real — see [Engines: database](../engines/database.md) for
the full picture, and swap `driver="algolia"` in step 3 below if you want
this app on Algolia instead; nothing else in this tutorial changes.

All code below is verified end to end (via FastAPI's `TestClient`) before
being written down here — not just sketched and assumed to work.

## Prerequisites

- Python 3.9+

```bash
pip install "fiction-scout[sqlalchemy]" fastapi uvicorn
```

## 1. Project layout

```
movies_api/
├── database.py
├── models.py
├── schemas.py
└── main.py
```

## 2. Database + fiction-scout wiring

Unlike Django, SQLAlchemy has no settings-style implicit registry to
auto-discover a connection from — `runtime.configure()` is the one-time
call that wires fiction-scout to your `sessionmaker`. It's also what
connects the `before_commit`/`after_commit` sync hooks (SQLAlchemy's
equivalent of Django's `post_save`/`post_delete` signals — see
[Indexing: auto-sync](../indexing.md#auto-sync-on-savedelete) for why the
two mechanisms are deliberately different, not just differently spelled).

```python
# database.py
from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from fiction_scout.adapters.sqlalchemy import runtime


class Base(DeclarativeBase):
    pass


engine = create_engine("sqlite:///./movies.db")
Session = sessionmaker(bind=engine)

# driver defaults to "database" — nothing else to configure for this tutorial.
runtime.configure(session_factory=Session)
```

`sqlite:///./movies.db` (a real file), not `sqlite:///:memory:` — SQLAlchemy
hands out a fresh connection per `Session()` call by default, and each
connection to `:memory:` is its own separate, empty database unless you
explicitly configure connection pooling to share one. A real file (or a real
server-based database) doesn't have this trap.

## 3. The `Movie` model

```python
# models.py
from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Mapped, mapped_column

from database import Base
from fiction_scout.adapters.sqlalchemy.mixin import SearchableMixin
from fiction_scout.strategies import search_using_full_text, search_using_prefix


class Movie(SearchableMixin, Base):
    __tablename__ = "movies"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(index=True)
    description: Mapped[str]
    director: Mapped[str] = mapped_column(index=True)
    category: Mapped[str] = mapped_column(index=True)
    release_year: Mapped[int]

    @search_using_prefix("title")
    @search_using_full_text("description")
    def to_searchable_array(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "director": self.director,
            "category": self.category,
            "release_year": self.release_year,
        }
```

`director`/`category` are plain string columns, not relationships to a
`Director`/`Category` table — deliberately, same reasoning as the Django
tutorial. It also sidesteps a real current limitation worth knowing about:
`SQLAlchemyAdapter.apply_where()` resolves `field` as a **direct attribute
name** on the model (`getattr(model, field)`) — unlike Django's adapter,
which delegates to `QuerySet.filter(**{field: value})` and gets `__`-relation
traversal (`director__name`) for free. Against the `database` driver here,
`.where("director", "...")` only works because `director` really is a flat
column. See [Searching: where clauses](../searching.md#where-clauses) for
the full engine-by-engine breakdown, including the `.query(callback)`
escape hatch for expressing a real join/relationship filter.

## 4. Pydantic schemas

```python
# schemas.py
from __future__ import annotations

from pydantic import BaseModel


class MovieCreate(BaseModel):
    title: str
    description: str
    director: str
    category: str
    release_year: int


class MovieOut(BaseModel):
    id: int
    title: str
    description: str
    director: str
    category: str
    release_year: int

    model_config = {"from_attributes": True}
```

## 5. The FastAPI app

```python
# main.py
from __future__ import annotations

from typing import Optional

from fastapi import FastAPI

from database import Base, Session, engine
from models import Movie
from schemas import MovieCreate, MovieOut

Base.metadata.create_all(engine)

app = FastAPI(title="Movies API")


@app.post("/movies", response_model=MovieOut, status_code=201)
def create_movie(payload: MovieCreate) -> Movie:
    with Session() as session:
        movie = Movie(**payload.model_dump())
        session.add(movie)
        session.commit()  # synced to the index only once the transaction lands
        session.refresh(movie)
        return movie


@app.get("/movies", response_model=list[MovieOut])
def list_movies(
    q: str = "",
    director: Optional[str] = None,
    category: Optional[str] = None,
    page: int = 1,
    per_page: int = 15,
) -> list[Movie]:
    builder = Movie.search(q)
    if director:
        builder = builder.where("director", director)
    if category:
        builder = builder.where("category", category)
    return list(builder.paginate(per_page=per_page, page=page))
```

`Movie.search(q)` with `q=""` (no `q` param) matches the `database` driver's
own default: an empty term is treated as "no search filter," so
`Movie.search("").paginate()` returns every row, subject to whatever
`.where()` filters were chained — same "list + filter + search through one
code path" shape as the Django tutorial, for the same reason. `.where()` is
only called when the query param is actually present, same caveat as
before: `.where("director", None)` would build a real (and wrong)
`director IS NULL`-adjacent filter, not a no-op.

Saving via `session.commit()` triggers fiction-scout's `after_commit` hook
automatically — nothing in `create_movie` calls `.searchable()` directly.

## 6. Run it

```bash
uvicorn main:app --reload
```

```bash
curl -X POST http://localhost:8000/movies \
  -H "Content-Type: application/json" \
  -d '{"title": "Star Trek II: The Wrath of Khan", "description": "Khan Noonien Singh escapes exile and seeks revenge on Admiral Kirk.", "director": "Nicholas Meyer", "category": "Sci-Fi", "release_year": 1982}'

curl -X POST http://localhost:8000/movies \
  -H "Content-Type: application/json" \
  -d '{"title": "The Godfather", "description": "The aging patriarch of an organized crime dynasty transfers control to his son.", "director": "Francis Ford Coppola", "category": "Drama", "release_year": 1972}'
```

```bash
curl "http://localhost:8000/movies?q=khan"
curl "http://localhost:8000/movies?category=Drama"
curl "http://localhost:8000/movies?director=Nicholas+Meyer"
curl "http://localhost:8000/movies"   # everything, paginated
```

Interactive docs (from FastAPI's own auto-generated OpenAPI UI, unrelated to
fiction-scout) are at `http://localhost:8000/docs`.

## Next steps

- [Configuration](../configuration.md) — the full `FictionScoutConfig`
  reference; switching `driver` to `"algolia"`/`"meilisearch"` here needs
  only a config change, not a rewrite.
- [Extending: custom adapters](../extending/custom-adapters.md) — the
  `runtime.configure()`/`before_commit`/`after_commit` pattern this tutorial
  used, explained from the adapter-author's side.
- [Indexing](../indexing.md) — soft delete, conditionally-searchable
  records, pausing auto-sync for bulk imports.
