# fiction-scout — CLAUDE.md

Project-specific rules for working in this repository. These apply on top of
any global instructions.

## What this project is

A Python port of [Laravel Scout](https://laravel.com/docs/master/scout)'s
design: a driver-based full-text search layer that auto-syncs models to a
search index. Ships adapters for Django and SQLAlchemy, and two built-in
drivers (Database, Collection). See `README.md` for the pitch and
`ROADMAP.md` for what's in vs. out of v1.

## The one architectural rule that matters

**Core code (`engines/`, `search/builder.py`, `config.py`, `cli/`) never
imports Django or SQLAlchemy.** It only talks to the `SearchableAdapter`
protocol in `protocols.py`. If you're tempted to add an `if isinstance(model,
django.db.models.Model)` check anywhere outside `adapters/django/`, that's a
sign the logic belongs in the adapter, not in core. This is what makes adding
a third ORM adapter (Peewee, Tortoise, whatever) a pure-addition change
instead of a core rewrite. Verify this holds with:

```bash
grep -rn "^import django\|^from django\|^import sqlalchemy\|^from sqlalchemy" src/fiction_scout --include="*.py" | grep -v "src/fiction_scout/adapters/"
```

This should return nothing. If it does, that's a bug, not a style nit.

## DRY points to preserve

- The standalone CLI (`cli/commands/*.py`) and the Django management command
  bridge (`adapters/django/management/commands/fiction_scout.py`) must call
  the exact same functions. The management command is a thin argument-parsing
  wrapper — it must never reimplement import/flush/sync logic.
- The Django mixin and the SQLAlchemy mixin expose an identical public method
  surface (`to_searchable_array`, `searchable_as`, `get_scout_key`, `.search()`,
  `.searchable()`, `.unsearchable()`, `should_be_searchable`, etc.). Shared
  orchestration logic lives in core functions both mixins call — only the raw
  ORM data-access primitives (`chunk_records`, `apply_like_filter`, etc.)
  differ per adapter, because that's the one place duplication is structurally
  required.
- New search drivers register via `EngineManager.extend()` and reuse the
  dependency-validation mechanism already in `engines/manager.py` — don't
  hand-roll a new "is the SDK installed" check per driver.

## Coding standards

- **PEP 8** (https://peps.python.org/pep-0008/), enforced by `ruff` — run
  `ruff check .` and `ruff format .` before considering work done.
- Full type hints on every public function/method. `mypy --strict` runs on
  core; Django/SQLAlchemy adapter modules are checked less strictly (see
  `pyproject.toml` `[tool.mypy]` overrides) because their stub coverage is
  incomplete, not because rigor doesn't matter there.
- Do not add comments or docstrings unless strictly necessary. Default to
  none. A well-named function/class/variable and a clear signature should
  make the *what* self-evident — don't restate it in a docstring. The only
  thing worth writing down is a non-obvious *why*: a hidden constraint, a
  workaround, a reason a simpler approach doesn't work. See the SQLAlchemy
  `after_commit`-vs-`after_insert` choice in `adapters/sqlalchemy/events.py`
  for the bar to clear. `pyproject.toml`'s ruff config does not require
  docstrings on public modules/functions (`D100`-`D104`, `D106` are
  ignored) — that's deliberate, not an oversight to "fix" by adding them
  back.
- Write idiomatic, pythonic code: comprehensions over manual accumulation
  loops, `pathlib` over `os.path`, context managers over manual
  try/finally, unpacking over indexing, f-strings over `%`/`.format()`,
  `dataclasses`/`NamedTuple` over ad-hoc attribute bags. Prefer the
  standard-library idiom over a hand-rolled equivalent.

## Testing

- `pytest` with markers: `@pytest.mark.django`, `@pytest.mark.sqlalchemy`,
  `@pytest.mark.celery`. Core tests (`tests/engines`, `tests/search`,
  `tests/sync`, `tests/test_*.py`) carry no marker and must pass with **no**
  optional extras installed — this is the test that proves core has no hard
  ORM dependency.
- `nox -s test_core` runs core tests in isolation from a venv with no ORM
  extras installed. Don't skip this when changing anything in `engines/`,
  `search/`, or `config.py` — it's the actual proof of the architectural rule
  above, not a formality.
- New engine or adapter code needs a test proving the specific contract
  method it implements, not just a smoke test that it "runs."

## What not to do

- Don't implement Algolia/Meilisearch/Typesense drivers unless explicitly
  asked — they're deliberately deferred (see `ROADMAP.md`), and building them
  speculatively without a real SDK to test against produces untested code
  masquerading as a feature.
- Don't add async variants of the adapters. `sync/context.py`'s use of
  `contextvars` was a deliberate hook for that future work, not an invitation
  to build it now.
- Don't collapse the Django and SQLAlchemy sync-event choice into "the same
  mechanism" — they're intentionally different (signals vs. session
  `after_commit`) because SQLAlchemy needs to avoid indexing rows from a
  transaction that later rolls back, a problem Django's post-commit-adjacent
  signals don't have in the same way. If unifying this is ever proposed,
  re-derive from that constraint first.
