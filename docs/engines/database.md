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

Override per column with decorators from `fiction_scout.strategies`,
stacked on `to_searchable_array`:

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

Each decorator just records a `column -> strategy` mapping on the
`to_searchable_array` function (`fiction_scout.strategies.get_column_strategies`
reads it back); it doesn't touch the database at all. That mapping is
re-read on every `.search()` call, so there's no index to rebuild or
migration to run when you change one — see "Switching a column's strategy"
below.

### The three strategies

| Strategy | Decorator | Django lookup built | Matches | Typical use |
|---|---|---|---|---|
| `LIKE` (default) | *(none — applies automatically to auto-detected text columns)* | `column__icontains` | `term` anywhere in the column, case-insensitive | General free-text search; the safe default for anything undecorated |
| `PREFIX` | `search_using_prefix(*columns)` | `column__istartswith` | `term` only at the very start of the column | Autocomplete/typeahead, or an index-friendly match with no leading wildcard |
| `FULL_TEXT` | `search_using_full_text(*columns)` | `column__iregex` with a whole-word pattern (`\bterm\b`, or `\yterm\y` on Postgres — see below) | `term` as a whole word anywhere in the column | Free-text search inside long content, where "star" shouldn't also match "stardust" |

Concretely, given `body = "the star shone"`:

- `LIKE`: `.search("star")` matches — and so would `.search("stardust")`
  or `.search("costar")`, since it's a plain substring match.
- `PREFIX`: `.search("star")` does **not** match — the *column* doesn't
  start with `"star"` (it starts with `"the"`). `.search("the")` would.
- `FULL_TEXT`: `.search("star")` matches, but `.search("stardust")` and
  `.search("costar")` do not — only the whole word.

`search_using_full_text` builds a regex match, not a database-specific
full-text index — the word-boundary
escape differs by backend, since PostgreSQL's native regex engine doesn't
treat `\b` as a word-boundary escape the way SQLite/MySQL do (Postgres's
own escape is `\y`); the Django adapter detects the connection's vendor and
picks the right one automatically, so this needs no per-backend handling
from you. Swap in `django.contrib.postgres.search.SearchVector` yourself
for a real Postgres full-text index.

### Switching a column's strategy

Since the mapping is just `column -> strategy`, moving a column between
strategies is a one-line change — swap which decorator wraps the column,
leave everything else untouched:

```python
# Before: prefix match on "title"
@search_using_prefix("title")
def to_searchable_array(self) -> dict:
    ...
```

```python
# After: whole-word match on "title" instead — same column, same
# to_searchable_array body, just a different decorator.
@search_using_full_text("title")
def to_searchable_array(self) -> dict:
    ...
```

The reverse (`full_text` → `prefix`) is the same swap in the other
direction. Removing the decorator entirely drops the column back to the
`LIKE` default — as long as it's still an auto-detected text-like field on
the model (see "What gets decorated" below).

Two things worth knowing about how the decorators combine:

- **Multiple columns per call:** `@search_using_prefix("title", "slug")`
  applies the same strategy to both in one decorator.
- **Last decorator for a given column wins**, if you (unusually) decorate
  the same column with both strategies — `get_column_strategies` merges
  them into one `column -> strategy` dict, so there's no "both apply"
  state.

### What gets decorated

The string passed to `search_using_prefix`/`search_using_full_text` isn't
required to be a literal field on the model — it's resolved as a Django ORM
lookup path, exactly like `.where()` (see
[Where clause fields are real query paths](#where-clause-fields-are-real-query-paths)
below). That means you can reach across a relation with `__`:

```python
class Movie(SearchableMixin, models.Model):
    director = models.ForeignKey(Director, on_delete=models.CASCADE)

    @search_using_prefix("director__name")
    def to_searchable_array(self) -> dict:
        return {"id": self.id, "director": self.director.name}
```

`Movie.search("Nolan")` now prefix-matches against the related
`Director.name` directly — even though `to_searchable_array()`'s
`"director"` key holds a plain string, not the relation path. Strategy
columns and `.where()` fields both resolve against the real ORM, never
against `to_searchable_array()`'s keys.

**One thing decorators can't rescue on their own:** a column with *no*
decorator only joins the `LIKE` default if it's a real text-like field
recognized on the model (`CharField`, `TextField`, `SlugField`,
`EmailField`, `URLField`). A `ForeignKey` like `director` above is never
auto-included — decorate the relation path explicitly if you want it
searched.

## What it supports that external engines don't

`Builder.where()`/`.where_in()`/`.where_not_in()` and `.with_trashed()`/
`.only_trashed()` are fully honored by this engine (it builds a real
`QuerySet`/`Select`) — they are **not** translated into filter syntax for
Algolia or Meilisearch in v1. If your app needs those, run against
`database` or `collection`.

## Where clause fields are real query paths

Because this engine filters the live table directly, the field name passed
to `.where()`/`.where_in()`/`.where_not_in()` is resolved as an actual
Django ORM query path — exactly as if you'd written
`Model.objects.filter(...)` by hand — **not** a key of
`to_searchable_array()`. For a `ForeignKey`, that means using Django's `__`
relation-traversal syntax to reach a related field:

```python
class Movie(SearchableMixin, models.Model):
    director = models.ForeignKey(Director, on_delete=models.CASCADE)

    def to_searchable_array(self) -> dict:
        return {"id": self.id, "director": self.director.name}
```

```python
# Wrong on `database`: "director" resolves to the FK column (an integer
# id), not the related Director's name — even though to_searchable_array()
# has a "director" key holding the name.
Movie.search().where_in("director", ["Peter Jackson"])   # raises ValueError

# Right: traverse the relation the same way you would on a raw queryset.
Movie.search().where_in("director__name", ["Peter Jackson"])
```

See [Searching: where clauses](../searching.md#where-clauses) for how this
contrasts with `collection`/`algolia`/`meilisearch`, where the field
resolves against `to_searchable_array()` instead.
