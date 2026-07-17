from __future__ import annotations

import pytest

from fiction_scout.dependencies import require_installed
from fiction_scout.exceptions import MissingDependencyError


def test_require_installed_passes_for_an_installed_module() -> None:
    require_installed("core", "os", "n/a")  # must not raise


def test_require_installed_raises_with_actionable_message() -> None:
    with pytest.raises(MissingDependencyError) as excinfo:
        require_installed("algolia", "algoliasearch", "algolia")
    message = str(excinfo.value)
    assert "algoliasearch" in message
    assert 'pip install "fiction-scout[algolia]"' in message
