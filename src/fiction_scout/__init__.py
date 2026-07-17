"""fiction-scout: driver-based full-text search for Django, Flask, and any Python project."""

from __future__ import annotations

from fiction_scout.config import FictionScoutConfig, resolve_config
from fiction_scout.engines.base import Engine, Page
from fiction_scout.engines.manager import EngineManager
from fiction_scout.exceptions import (
    FictionScoutError,
    MissingDependencyError,
    UnknownDriverError,
)
from fiction_scout.search.builder import Builder
from fiction_scout.sync.context import is_syncing_paused, without_syncing_to_search

__version__ = "0.1.0"

__all__ = [
    "Builder",
    "Engine",
    "EngineManager",
    "FictionScoutConfig",
    "FictionScoutError",
    "MissingDependencyError",
    "Page",
    "UnknownDriverError",
    "__version__",
    "is_syncing_paused",
    "resolve_config",
    "without_syncing_to_search",
]
