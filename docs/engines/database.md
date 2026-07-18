# `database` engine

The default driver (`FICTION_SCOUT = {"driver": "database"}`, or no config
at all). Searches a model's existing table directly — there's no separate
index, no sync step, and `update`/`delete`/`flush` are all no-ops, since
results always reflect current database state.

## Column matching

By default, every text-like column (Django: `CharField`, `TextField`,
`SlugField`, `EmailField`, `URLField`) is matched with a
`LIKE '%term%'`-style query, auto-detected from the model — no
configuration needed for basic search to work.

Override per column with decorators from `fiction_scout.strategies`:

```python
from fiction_scout.strategies import search_using_full_text, search_using_prefix


class Post(SearchableMixin, models.Model):
    title = models.CharField(max_length=200)
    body = models.TextField()

    @search_using_prefix("title")
    @search_using_full_text("body")
    def to_searchable_array(self) -> dict:
        return {"id": self.id, "title": self.title, "body": self.body}
```

- `search_using_prefix(*columns)` — matches `term%` only (an index-friendly
  prefix match, e.g. for autocomplete).
- `search_using_full_text(*columns)` — matches whole words
  (`\bterm\b`-style), not a database-specific full-text index. The Django
  adapter implements this as a whole-word regex match so behavior is
  identical on SQLite and Postgres; swap in
  `django.contrib.postgres.search.SearchVector` yourself for a real
  Postgres full-text index.

Undecorated text columns default to `LIKE`.

## What it supports that external engines don't

`Builder.where()`/`.where_in()`/`.where_not_in()` and `.with_trashed()`/
`.only_trashed()` are fully honored by this engine (it builds a real
`QuerySet`/`Select`) — they are **not** translated into filter syntax for
Algolia or Meilisearch in v1. If your app needs those, run against
`database` or `collection`.
