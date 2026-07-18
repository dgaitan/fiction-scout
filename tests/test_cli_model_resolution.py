from __future__ import annotations

import pytest

from fiction_scout.cli.model_resolution import resolve_model
from fiction_scout.exceptions import ModelResolutionError


def test_given_valid_dotted_path_when_resolve_model_called_then_returns_class() -> None:
    model = resolve_model("tests.support.Article")

    assert model.__name__ == "Article"


def test_given_unimportable_module_when_resolve_model_called_then_raises() -> None:
    with pytest.raises(ModelResolutionError, match="Could not import"):
        resolve_model("tests.no_such_module.Article")


def test_given_missing_class_on_real_module_when_resolve_model_called_then_raises() -> (
    None
):
    with pytest.raises(ModelResolutionError, match="Could not import"):
        resolve_model("tests.support.NoSuchClass")


def test_given_path_with_no_module_when_resolve_model_called_then_raises() -> None:
    with pytest.raises(ModelResolutionError, match="Could not import"):
        resolve_model("NoDotsHere")
