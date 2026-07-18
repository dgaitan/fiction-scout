from __future__ import annotations

import pytest

from fiction_scout.dependencies import require_installed
from fiction_scout.exceptions import MissingDependencyError


def test_require_installed_passes_for_an_installed_module() -> None:
    require_installed("core", "os", "n/a")  # must not raise


def test_require_installed_raises_with_actionable_message() -> None:
    # A module name that is never a real fiction-scout extra, so this test
    # stays true regardless of which optional extras happen to be installed
    # in the environment it runs in.
    with pytest.raises(MissingDependencyError) as excinfo:
        require_installed("widget", "definitely_not_a_real_package", "widget")
    message = str(excinfo.value)
    assert "definitely_not_a_real_package" in message
    assert 'pip install "fiction-scout[widget]"' in message
