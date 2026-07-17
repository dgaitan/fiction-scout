from __future__ import annotations

import pytest

from fiction_scout.registry import Registry


def test_resolve_builds_and_caches_the_instance() -> None:
    calls = []

    def factory() -> object:
        calls.append(1)
        return object()

    registry: Registry[object] = Registry()
    registry.register("thing", factory)

    first = registry.resolve("thing")
    second = registry.resolve("thing")

    assert first is second
    assert len(calls) == 1


def test_resolve_unknown_name_raises_key_error() -> None:
    registry: Registry[object] = Registry()
    with pytest.raises(KeyError):
        registry.resolve("missing")


def test_available_lists_registered_names_sorted() -> None:
    registry: Registry[object] = Registry()
    registry.register("b", object)
    registry.register("a", object)
    assert registry.available() == ["a", "b"]


def test_re_registering_drops_the_cached_instance() -> None:
    registry: Registry[str] = Registry()
    registry.register("thing", lambda: "first")
    assert registry.resolve("thing") == "first"

    registry.register("thing", lambda: "second")
    assert registry.resolve("thing") == "second"


def test_forget_one_name_leaves_others_cached() -> None:
    registry: Registry[object] = Registry()
    registry.register("a", object)
    registry.register("b", object)
    a = registry.resolve("a")
    b = registry.resolve("b")

    registry.forget("a")

    assert registry.resolve("a") is not a
    assert registry.resolve("b") is b


def test_forget_all_clears_every_cached_instance() -> None:
    registry: Registry[object] = Registry()
    registry.register("a", object)
    a = registry.resolve("a")

    registry.forget()

    assert registry.resolve("a") is not a
