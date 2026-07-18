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


# pytest imports every test module during collection before marker-based
# deselection (`-m ...`) ever runs, so an ORM-specific test file that
# imports Django/SQLAlchemy at module level breaks collection in an
# extras-free environment even though none of its tests would have run
# there. `--ignore` skips collection entirely — the actual enforcement
# mechanism behind "core has no hard ORM dependency", not just the marker.
_DJANGO_TEST_PATHS = ["tests/django_app", "tests/test_django"]
_SQLALCHEMY_TEST_PATHS = ["tests/sqlalchemy_app", "tests/test_sqlalchemy"]


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
        "not django and not sqlalchemy and not celery",
        *(f"--ignore={path}" for path in _DJANGO_TEST_PATHS + _SQLALCHEMY_TEST_PATHS),
    )


@nox.session(python=PYTHON_VERSIONS)
def test_django(session: nox.Session) -> None:
    """Run the Django adapter test suite."""
    session.install("-e", ".[dev,django]")
    session.run(
        "pytest",
        "tests",
        "-m",
        "django",
        *(f"--ignore={path}" for path in _SQLALCHEMY_TEST_PATHS),
        env={"DJANGO_SETTINGS_MODULE": "tests.django_app.settings"},
    )


@nox.session(python=PYTHON_VERSIONS)
def test_sqlalchemy(session: nox.Session) -> None:
    """Run the SQLAlchemy adapter test suite."""
    session.install("-e", ".[dev,sqlalchemy]")
    session.run(
        "pytest",
        "tests",
        "-m",
        "sqlalchemy",
        *(f"--ignore={path}" for path in _DJANGO_TEST_PATHS),
    )


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
