"""Tests for the decorator-based registry."""

import pytest

from busbidder.exceptions import RegistryError
from busbidder.registry import Registry


class Plugin:
    name = ""


class NotAPlugin:
    pass


@pytest.fixture
def registry() -> Registry[Plugin]:
    return Registry("plugin", Plugin)


def test_register_and_create(registry: Registry[Plugin]) -> None:
    @registry.register("alpha")
    class Alpha(Plugin):
        pass

    assert Alpha.name == "alpha"
    assert "alpha" in registry
    assert registry.get("alpha") is Alpha
    assert isinstance(registry.create("alpha"), Alpha)
    assert registry.names() == ["alpha"]


def test_names_keep_registration_order(registry: Registry[Plugin]) -> None:
    for name in ("zulu", "alpha", "mike"):
        registry.register(name)(type(name, (Plugin,), {}))
    assert registry.names() == ["zulu", "alpha", "mike"]
    assert list(registry) == ["zulu", "alpha", "mike"]


def test_duplicate_name_is_rejected(registry: Registry[Plugin]) -> None:
    @registry.register("alpha")
    class Alpha(Plugin):
        pass

    with pytest.raises(RegistryError, match="duplicate"):

        @registry.register("alpha")
        class Other(Plugin):
            pass


def test_wrong_base_class_is_rejected(registry: Registry[Plugin]) -> None:
    with pytest.raises(RegistryError, match="not a subclass"):
        registry.register("bad")(NotAPlugin)  # type: ignore[arg-type]


def test_invalid_name_is_rejected(registry: Registry[Plugin]) -> None:
    with pytest.raises(RegistryError, match="invalid"):
        registry.register("two words")


def test_unknown_name_lists_known_names(registry: Registry[Plugin]) -> None:
    @registry.register("alpha")
    class Alpha(Plugin):
        pass

    with pytest.raises(RegistryError, match="known: alpha"):
        registry.get("beta")
