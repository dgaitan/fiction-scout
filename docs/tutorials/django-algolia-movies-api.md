# Tutorial: Movies API with Django + Algolia

We'll build a small Movies API: list movies, filter by `director` and
`category`, and full-text search title/description — all backed by Algolia
through fiction-scout, with auto-sync on every save via Django's own
`post_save` signal.

See [Tutorials overview](index.md) for how this compares to the
[FastAPI + SQLAlchemy](fastapi-sqlalchemy-movies-api.md) version of the same
app.

## Prerequisites

- Python 3.9+
- An [Algolia](https://www.algolia.com/) account (the free tier is enough)
  — grab your **Application ID** and an **Admin API Key** from the Algolia
  dashboard's API Keys page. The Admin key is required, not the
  search-only key — fiction-scout writes to the index (`save_objects`,
  `set_settings`), which the search-only key can't do.

## 1. Project setup

```bash
django-admin startproject moviesapi
cd moviesapi
python manage.py startapp movies
pip install "fiction-scout[django,algolia]"
```

## 2. The `Movie` model

```python
# movies/models.py
from __future__ import annotations

from typing import Any

from django.db import models

from fiction_scout.adapters.django.mixin import SearchableMixin
from fiction_scout.strategies import search_using_full_text, search_using_prefix


class Movie(SearchableMixin, models.Model):
    title = models.CharField(max_length=200)
    description = models.TextField()
    director = models.CharField(max_length=200)
    category = models.CharField(max_length=100)
    release_year = models.PositiveIntegerField()

    def __str__(self) -> str:
        return self.title

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

`director` and `category` are plain `CharField`s, not `ForeignKey`s — on
purpose. Algolia (and `to_searchable_array()` generally) works against
whatever this method returns, so a related object's *name*, not its id, is
what needs to end up in the index. Keeping them as flat strings here avoids
that translation step entirely; see
[Searching: where clauses](../searching.md#where-clauses) if your real app
needs `director` to stay a real `ForeignKey` — you'd resolve
`self.director.name` inside `to_searchable_array()` instead, the field name
in the index doesn't have to match the model's own field name.

The `@search_using_prefix`/`@search_using_full_text` decorators only matter
if you also configure the `database` driver — Algolia entirely ignores them
and searches whatever `searchable_attributes` you configure in step 4. They're
included here so switching `FICTION_SCOUT["driver"]` to `"database"` later
(e.g. for local dev without an Algolia account) works with no other changes.

## 3. Settings

```python
# moviesapi/settings.py
INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "fiction_scout.adapters.django",
    "movies",
]

FICTION_SCOUT = {
    "driver": "algolia",
    "algolia_app_id": "YOUR_APP_ID",       # or set ALGOLIA_APP_ID instead
    "algolia_api_key": "YOUR_ADMIN_KEY",   # or set ALGOLIA_API_KEY instead
    "index_settings": {
        "movies.models.Movie": {
            "searchable_attributes": ["title", "description"],
            "attributes_for_faceting": ["director", "category"],
        },
    },
}
```

**`attributes_for_faceting` is not optional** — `.where("director", ...)`/
`.where("category", ...)` fail with `UnfilterableAttributeError` against any
attribute not declared here. This is fiction-scout translating Algolia's own
requirement into a clear error instead of a raw `400` — see
[Algolia: Error handling](../engines/algolia.md#error-handling) for the full
list of translated exceptions. Prefer env vars over hardcoding credentials in
`settings.py` — leave `algolia_app_id`/`algolia_api_key` out entirely and set
`ALGOLIA_APP_ID`/`ALGOLIA_API_KEY` instead; both env vars are checked as a
fallback automatically.

## 4. Migrate and apply the index settings

```bash
python manage.py migrate
python manage.py fiction_scout sync-index-settings movies.models.Movie
```

The second command pushes `searchable_attributes`/`attributes_for_faceting`
from `settings.py` to Algolia. Run it again any time you change
`index_settings` for this model — it's idempotent, safe to re-run.

## 5. Seed some movies

```bash
python manage.py shell
```

```python
from movies.models import Movie

Movie.objects.create(
    title="Star Trek II: The Wrath of Khan",
    description="Khan Noonien Singh escapes exile and seeks revenge on Admiral Kirk.",
    director="Nicholas Meyer",
    category="Sci-Fi",
    release_year=1982,
)
Movie.objects.create(
    title="The Godfather",
    description="The aging patriarch of an organized crime dynasty transfers control to his son.",
    director="Francis Ford Coppola",
    category="Drama",
    release_year=1972,
)
Movie.objects.create(
    title="Star Wars: Episode IV - A New Hope",
    description="A young farm boy joins a rebellion against an evil galactic empire.",
    director="George Lucas",
    category="Sci-Fi",
    release_year=1977,
)
```

Each `Movie.objects.create(...)` fires Django's `post_save` signal, which
fiction-scout's `SearchableMixin` connects automatically in
`AppConfig.ready()` — every movie above is already searchable in Algolia
with no further steps. If you're importing an existing table instead of
creating fresh rows, use the bulk-import command:

```bash
python manage.py fiction_scout import movies.models.Movie
```

## 6. The API view

A plain Django view — no DRF required. `q`/`director`/`category` are all
optional and combine: `?q=star&category=Sci-Fi` searches "star" *and*
filters to Sci-Fi in one request.

```python
# movies/views.py
from __future__ import annotations

from django.http import JsonResponse
from django.views.decorators.http import require_GET

from movies.models import Movie


@require_GET
def list_movies(request):
    term = request.GET.get("q", "")
    director = request.GET.get("director")
    category = request.GET.get("category")
    page = int(request.GET.get("page", 1))
    per_page = int(request.GET.get("per_page", 15))

    builder = Movie.search(term)
    if director:
        builder = builder.where("director", director)
    if category:
        builder = builder.where("category", category)

    result = builder.paginate(per_page=per_page, page=page)

    return JsonResponse(
        {
            "results": [
                {
                    "id": movie.id,
                    "title": movie.title,
                    "description": movie.description,
                    "director": movie.director,
                    "category": movie.category,
                    "release_year": movie.release_year,
                }
                for movie in result
            ],
            "total": result.total,
            "page": result.page,
            "per_page": result.per_page,
            "has_more": result.has_more,
        }
    )
```

`Movie.search(term)` with `term=""` (no `q` param) is a valid, deliberate
call — Algolia treats an empty query as "match everything," so the endpoint
naturally supports "list all movies, optionally filtered" and "search"
through the exact same code path. `.where()` is only called when the
corresponding query param is actually present — calling `.where("director",
None)` would build a real (and wrong) `director:'None'` filter, not a no-op.

```python
# movies/urls.py
from django.urls import path

from movies import views

urlpatterns = [
    path("movies", views.list_movies, name="list_movies"),
]
```

```python
# moviesapi/urls.py
from django.urls import include, path

urlpatterns = [
    path("api/", include("movies.urls")),
]
```

## 7. Try it

```bash
python manage.py runserver
```

```bash
curl "http://localhost:8000/api/movies?q=khan"
curl "http://localhost:8000/api/movies?category=Sci-Fi"
curl "http://localhost:8000/api/movies?director=George%20Lucas"
curl "http://localhost:8000/api/movies?q=star&category=Sci-Fi"
curl "http://localhost:8000/api/movies"   # everything, paginated
```

## Troubleshooting

| Symptom | Cause |
|---|---|
| `UnfilterableAttributeError` on `?director=...` | `attributes_for_faceting` doesn't include `director` — re-check step 3, then re-run `sync-index-settings`. |
| `EngineConnectionError` (looks like a network outage) | Almost always a typo'd `algolia_app_id` — Algolia derives the request hostname from the app id, so a wrong one fails DNS resolution rather than returning an auth error. |
| A movie doesn't show up in search results | Confirm it was actually created via `.save()`/`.objects.create()`, not a bulk operation (`bulk_create` bypasses signals — see [Indexing: pausing sync during bulk operations](../indexing.md#pausing-sync-during-bulk-operations)) after the app was already running with `post_save` connected. |

## Next steps

- [Configuration](../configuration.md) — the full `FICTION_SCOUT` reference,
  including multi-tenancy via `index_prefix`.
- [Algolia engine reference](../engines/algolia.md) — every accepted
  `index_settings` key, with examples.
- [Indexing](../indexing.md) — soft delete, conditionally-searchable
  records (e.g. hide unpublished movies), pausing auto-sync for bulk
  imports.
