"""Configuration resolution.

Priority order: an explicitly-constructed `FictionScoutConfig` always wins.
Otherwise, Django settings are checked, then Flask app config, then
environment variables, falling back to defaults so the package works with
zero configuration.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field, replace
from typing import Any, Callable

DEFAULT_DRIVER = "database"
DEFAULT_CHUNK_SIZE = 500


@dataclass(frozen=True)
class FictionScoutConfig:
    """Resolved fiction-scout settings.

    Construct directly for standalone/plain-Python use, or call
    `resolve_config()` to auto-detect settings from Django, Flask, or the
    environment.
    """

    driver: str = DEFAULT_DRIVER
    soft_delete: bool = False
    chunk_size: int = DEFAULT_CHUNK_SIZE
    queue: bool = False
    index_prefix: str = ""
    extra: dict[str, Any] = field(default_factory=dict)

    def with_overrides(self, **overrides: Any) -> FictionScoutConfig:
        """Return a copy of this config with the given fields overridden."""
        return replace(self, **overrides)


_KNOWN_FIELDS = ("driver", "soft_delete", "chunk_size", "queue", "index_prefix")


def _from_mapping(data: dict[str, Any]) -> FictionScoutConfig:
    known = {name: data[name] for name in _KNOWN_FIELDS if name in data}
    extra = {key: value for key, value in data.items() if key not in _KNOWN_FIELDS}
    return FictionScoutConfig(**known, extra=extra)


def _resolve_django() -> FictionScoutConfig | None:
    try:
        from django.conf import settings  # type: ignore[import-not-found]
    except ImportError:
        return None
    if not settings.configured:
        return None
    data = getattr(settings, "FICTION_SCOUT", None)
    if data is None:
        return None
    return _from_mapping(data)


def _resolve_flask() -> FictionScoutConfig | None:
    try:
        from flask import current_app  # type: ignore[import-not-found]
    except ImportError:
        return None
    try:
        data = current_app.config.get("FICTION_SCOUT")
    except RuntimeError:
        return None  # Outside of a Flask application/request context.
    if data is None:
        return None
    return _from_mapping(data)


def _resolve_environment() -> FictionScoutConfig | None:
    if "FICTION_SCOUT_DRIVER" not in os.environ:
        return None
    return FictionScoutConfig(
        driver=os.environ.get("FICTION_SCOUT_DRIVER", DEFAULT_DRIVER),
        soft_delete=os.environ.get("FICTION_SCOUT_SOFT_DELETE", "").lower() == "true",
        chunk_size=int(os.environ.get("FICTION_SCOUT_CHUNK_SIZE", DEFAULT_CHUNK_SIZE)),
        queue=os.environ.get("FICTION_SCOUT_QUEUE", "").lower() == "true",
        index_prefix=os.environ.get("FICTION_SCOUT_INDEX_PREFIX", ""),
    )


_RESOLVERS: list[Callable[[], FictionScoutConfig | None]] = [
    _resolve_django,
    _resolve_flask,
    _resolve_environment,
]


def resolve_config(explicit: FictionScoutConfig | None = None) -> FictionScoutConfig:
    """Resolve settings: explicit config, then Django, then Flask, then env, then defaults.

    An explicitly passed `FictionScoutConfig` always wins outright — nothing
    below it runs. Otherwise each resolver in `_RESOLVERS` runs in order; the
    first one that finds applicable settings wins.
    """
    if explicit is not None:
        return explicit
    for resolver in _RESOLVERS:
        result = resolver()
        if result is not None:
            return result
    return FictionScoutConfig()
