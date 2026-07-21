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


class ModelResolutionError(FictionScoutError):
    """A dotted model path (e.g. `myapp.models.Post`) could not be imported."""

    def __init__(self, dotted_path: str, reason: str | None = None) -> None:
        self.dotted_path = dotted_path
        detail = f": {reason}" if reason else ""
        super().__init__(f"Could not import model '{dotted_path}'{detail}")


class IndexSettingsNotSupportedError(FictionScoutError):
    """A driver has no index-settings management to apply."""

    def __init__(self, driver_name: str) -> None:
        self.driver_name = driver_name
        super().__init__(
            f"The '{driver_name}' driver does not support index settings management."
        )


class IndexCreationNotSupportedError(FictionScoutError):
    """A driver has no explicit index-creation API to call."""

    def __init__(self, driver_name: str, reason: str) -> None:
        self.driver_name = driver_name
        self.reason = reason
        super().__init__(
            f"The '{driver_name}' driver does not support create_index: {reason}"
        )


class MissingCredentialsError(FictionScoutError):
    """A driver was constructed without credentials it needs to make requests."""

    def __init__(self, driver_name: str, missing: Sequence[str], hint: str) -> None:
        self.driver_name = driver_name
        self.missing = list(missing)
        joined = " and ".join(self.missing)
        super().__init__(f"The '{driver_name}' driver is missing {joined}. {hint}")


class EngineAuthenticationError(FictionScoutError):
    """A search engine rejected the configured credentials."""

    def __init__(self, driver_name: str, detail: str, hint: str) -> None:
        self.driver_name = driver_name
        self.detail = detail
        super().__init__(
            f"The '{driver_name}' driver's credentials were rejected: {detail} {hint}"
        )


class EngineConnectionError(FictionScoutError):
    """A search engine's API could not be reached."""

    def __init__(self, driver_name: str, detail: str, hint: str) -> None:
        self.driver_name = driver_name
        self.detail = detail
        super().__init__(f"Could not reach the '{driver_name}' API: {detail} {hint}")


class UnfilterableAttributeError(FictionScoutError):
    """A `.where()`/`.where_in()`/`.where_not_in()` field isn't filterable."""

    def __init__(self, driver_name: str, detail: str, hint: str) -> None:
        self.driver_name = driver_name
        self.detail = detail
        super().__init__(
            f"The '{driver_name}' driver rejected a filter: {detail} {hint}"
        )
