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
    session.install("-e", ".[dev,django,sqlalchemy]")
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
    session.run("pytest", "tests", "-m", "not django and not sqlalchemy and not celery")


@nox.session(python=PYTHON_VERSIONS)
def test_django(session: nox.Session) -> None:
    """Run the Django adapter test suite."""
    session.install("-e", ".[dev,django]")
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


@nox.session(python=PYTHON_VERSIONS[-1])
def test_all(session: nox.Session) -> None:
    """Run the full test suite with every extra installed."""
    session.install("-e", ".[dev,django,sqlalchemy,celery]")
    session.run("pytest", "tests", "--cov=fiction_scout", "--cov-report=term-missing")


@nox.session(python=PYTHON_VERSIONS[-1])
def smoke(session: nox.Session) -> None:
    """Run the runnable example apps as an end-to-end wiring check."""
    session.install("-e", ".[dev,django,sqlalchemy]")
    session.run("python", "examples/sqlalchemy_example/app.py")
