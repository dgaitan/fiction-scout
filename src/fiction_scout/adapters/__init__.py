"""ORM-specific implementations of the `SearchableAdapter` protocol.

Each subpackage (`django`, `sqlalchemy`) is independently importable and
requires only its own optional extra — importing `fiction_scout` itself
never requires Django or SQLAlchemy to be installed.
"""
