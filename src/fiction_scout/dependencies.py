"""Shared "is the SDK installed" check.

One mechanism, reused by anything that resolves a name to an implementation
backed by an optional extra — `EngineManager` (validating a search driver's
SDK) and the Celery dispatcher (validating `celery` itself) both call
:func:`require_installed` rather than hand-rolling their own check.
"""

from __future__ import annotations

import importlib.util

from fiction_scout.exceptions import MissingDependencyError


def require_installed(feature: str, module_name: str, extra: str) -> None:
    """Raise `MissingDependencyError` if `module_name` isn't importable.

    Args:
        feature: Human-readable name of the thing that needs it (e.g. a
            driver or dispatcher name), used in the error message.
        module_name: The importable module name to check for, e.g. `"celery"`.
        extra: The fiction-scout pip extra that installs it, e.g. `"celery"`,
            surfaced in the error message as `pip install "fiction-scout[extra]"`.
    """
    if importlib.util.find_spec(module_name) is None:
        raise MissingDependencyError(feature=feature, package=module_name, extra=extra)
