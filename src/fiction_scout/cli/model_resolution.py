"""Resolves a dotted import path (e.g. `myapp.models.Post`) to a model class."""

from __future__ import annotations

import importlib

from fiction_scout.exceptions import ModelResolutionError
from fiction_scout.protocols import ScoutModel


def resolve_model(dotted_path: str) -> type[ScoutModel]:
    """Import and return the class named at the end of `dotted_path`."""
    module_path, _, class_name = dotted_path.rpartition(".")
    if not module_path:
        raise ModelResolutionError(dotted_path, reason="expected a dotted path")
    try:
        module = importlib.import_module(module_path)
    except ImportError as exc:
        raise ModelResolutionError(dotted_path, reason=str(exc)) from exc
    try:
        model = getattr(module, class_name)
    except AttributeError as exc:
        raise ModelResolutionError(dotted_path, reason=str(exc)) from exc
    if not isinstance(model, type):
        raise ModelResolutionError(dotted_path, reason=f"{class_name!r} is not a class")
    return model


def model_dotted_path(model: type) -> str:
    """Return the dotted path that re-imports `model` (inverse of `resolve_model`)."""
    return f"{model.__module__}.{model.__qualname__}"
