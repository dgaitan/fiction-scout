"""Nox session definitions for fiction-scout's lint/typecheck/test matrix."""

import nox

nox.options.default_venv_backend = "uv"

PYTHON_VERSIONS = ["3.9", "3.10", "3.11", "3.12", "3.13"]


@nox.session(python=PYTHON_VERSIONS[-1])
def lint(session: nox.Session) -> None:
    """Run ruff lint and format checks."""
    session.install("-e", ".[dev]")
    session.run("ruff", "check", ".")
    session.run("ruff", "format", "--check", ".")


@nox.session(python=PYTHON_VERSIONS[-1])
def typecheck(session: nox.Session) -> None:
    """Run mypy against the core package."""
    session.install("-e", ".[dev,django,sqlalchemy,celery,algolia,meilisearch]")
    session.run("mypy")


# tests/conftest.py's `collect_ignore` is what actually keeps each ORM's
# test directory out of collection in an extras-free environment (it fires
# before `-m` marker deselection ever runs, and before nox even gets
# involved) — these sessions only need `-m` to select the right subset.


@nox.session(python=PYTHON_VERSIONS)
def test_core(session: nox.Session) -> None:
    """Run core tests with no ORM extras installed.

    This is the proof that core has no hard dependency on Django or
    SQLAlchemy — it must pass without either extra present.
    """
    session.install("-e", ".[dev]")
    session.run(
        "pytest",
        "tests",
        "-m",
        "not django and not sqlalchemy and not celery and not algolia",
    )


@nox.session(python=PYTHON_VERSIONS)
def test_django(session: nox.Session) -> None:
    """Run the Django adapter test suite.

    Installs the `algolia` and `meilisearch` extras alongside `django` too:
    `tests/test_django/test_algolia_integration.py` and
    `test_meilisearch_integration.py` each prove the real `DjangoAdapter`
    round-trips correctly through their respective engine, which needs both
    installed together to even collect.
    """
    session.install("-e", ".[dev,django,algolia,meilisearch]")
    session.run(
        "pytest",
        "tests",
        "-m",
        "django",
        env={"DJANGO_SETTINGS_MODULE": "tests.django_app.settings"},
    )


@nox.session(python=PYTHON_VERSIONS)
def test_sqlalchemy(session: nox.Session) -> None:
    """Run the SQLAlchemy adapter test suite."""
    session.install("-e", ".[dev,sqlalchemy]")
    session.run("pytest", "tests", "-m", "sqlalchemy")


@nox.session(python=PYTHON_VERSIONS)
def test_celery(session: nox.Session) -> None:
    """Run the Celery dispatcher test suite."""
    session.install("-e", ".[dev,celery]")
    session.run("pytest", "tests", "-m", "celery")


@nox.session(python=PYTHON_VERSIONS)
def test_algolia(session: nox.Session) -> None:
    """Run the Algolia engine test suite."""
    session.install("-e", ".[dev,algolia]")
    session.run("pytest", "tests", "-m", "algolia")


@nox.session(python=PYTHON_VERSIONS)
def test_meilisearch(session: nox.Session) -> None:
    """Run the Meilisearch engine test suite.

    The live-server tier (`tests/test_meilisearch/test_meilisearch_live.py`)
    skips itself gracefully here if neither a `meilisearch` binary is on
    `PATH` nor `MEILISEARCH_TEST_URL` is set — see that module's
    `conftest.py`. Export `MEILISEARCH_TEST_URL` (e.g. pointed at a
    `getmeili/meilisearch` container) to exercise it for real.
    """
    session.install("-e", ".[dev,meilisearch]")
    session.run("pytest", "tests", "-m", "meilisearch")


@nox.session(python=PYTHON_VERSIONS[-1])
def test_all(session: nox.Session) -> None:
    """Run the full test suite with every extra installed.

    `DJANGO_SETTINGS_MODULE` must be set here too, not just in
    `test_django` — without it, `tests/test_django/` and `tests/cli/` are
    silently excluded via `tests/conftest.py`'s `collect_ignore`, and this
    session's "every extra installed" claim would be false for anything
    Django-related (found while adding the Algolia/Django integration
    tests, which otherwise never ran under this session at all).
    """
    session.install("-e", ".[dev,django,sqlalchemy,celery,algolia,meilisearch]")
    session.run(
        "pytest",
        "tests",
        "--cov=fiction_scout",
        "--cov-report=term-missing",
        env={"DJANGO_SETTINGS_MODULE": "tests.django_app.settings"},
    )


@nox.session(python=PYTHON_VERSIONS[-1])
def smoke(session: nox.Session) -> None:
    """Run the runnable example apps as an end-to-end wiring check."""
    session.install("-e", ".[dev,django,sqlalchemy]")
    session.run("python", "examples/sqlalchemy_example/app.py")
