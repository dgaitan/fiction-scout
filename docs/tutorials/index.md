# Tutorials

Two full walkthroughs building the **same app** — a Movies API that lists
movies, filters by director and category, and full-text searches title and
description — on different stacks:

| Tutorial | Framework | ORM adapter | Search engine |
|---|---|---|---|
| [Django + Algolia](django-algolia-movies-api.md) | Django | `adapters.django` | `algolia` — external, hosted, needs an Algolia account |
| [FastAPI + SQLAlchemy](fastapi-sqlalchemy-movies-api.md) | FastAPI | `adapters.sqlalchemy` | `database` — built-in, zero external dependencies |

Deliberately paired this way, not by coincidence: reading both back to back
shows what's genuinely shared across every fiction-scout app (the
`SearchableMixin` surface, `Model.search(term).where(...).get()`, auto-sync
on save/commit) versus what's real per-stack difference (how sync gets
wired up, how the mixin is configured, what `.where()` can and can't
express against each driver). Everywhere the two tutorials diverge, that
divergence is called out explicitly rather than glossed over.

Both tutorials build toward the same three endpoints:

```
GET /movies?q=<term>                    # full-text search
GET /movies?director=<name>             # exact-match filter
GET /movies?category=<name>             # exact-match filter
```

(any combination of `q`, `director`, `category` can be used together)

If you only need one of these stacks, skip straight to it — neither
tutorial depends on the other. If you're evaluating fiction-scout itself,
reading both is the fastest way to see the actual shape of the seam between
core and adapter that the rest of the [docs](../index.md) describe more
abstractly.
