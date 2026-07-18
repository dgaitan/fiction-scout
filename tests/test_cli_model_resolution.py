from __future__ import annotations

import pytest

from fiction_scout.cli.model_resolution import model_dotted_path, resolve_model
from fiction_scout.exceptions import ModelResolutionError
from tests.support import Article


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


def test_given_a_class_when_model_dotted_path_called_then_round_trips() -> None:
    path = model_dotted_path(Article)

    assert path == "tests.support.Article"
    assert resolve_model(path) is Article
