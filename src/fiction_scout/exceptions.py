"""Exception types raised by fiction-scout."""

from __future__ import annotations

from collections.abc import Sequence


class FictionScoutError(Exception):
    """Base class for every exception fiction-scout raises."""


class MissingDependencyError(FictionScoutError):
    """A selected driver or dispatcher's required package isn't installed."""

    def __init__(self, feature: str, package: str, extra: str) -> None:
        self.feature = feature
        self.package = package
        self.extra = extra
        super().__init__(
            f"'{feature}' requires the '{package}' package, which isn't "
            f'installed. Install it with: pip install "fiction-scout[{extra}]"'
        )


class UnknownDriverError(FictionScoutError):
    """A driver name has no registered engine factory."""

    def __init__(self, name: str, available: Sequence[str]) -> None:
        self.name = name
        self.available = list(available)
        available_text = (
            ", ".join(self.available) if self.available else "none registered"
        )
        super().__init__(
            f"Unknown driver '{name}'. Available drivers: {available_text}. "
            "Register a new one with EngineManager.extend(name, factory)."
        )
