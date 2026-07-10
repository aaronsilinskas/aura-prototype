"""Tests for engine.scene.SceneLocalRegistry.

SceneLocalRegistry maps item name → module for one scene's local rules (or
effects).  It shares its item-loading internals with PackRegistry (no
duplicated import/attr/isinstance/cache logic) but has no version concept.
"""

from __future__ import annotations

import sys

import pytest

from engine.packs import ItemTypeError, MissingItemAttributeError, UnknownItemError
from engine.scene import SceneLocalRegistry

# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------


MODULE_PREFIX = "tslr"


@pytest.fixture()
def local_env(tmp_path):
    """Yield a directory rooted under tmp_path as the registry source.

    ``tmp_path`` is inserted into ``sys.path`` so modules are importable.
    All imported modules added during the test are removed on teardown.
    """
    root = tmp_path / MODULE_PREFIX
    root.mkdir()
    sys.path.insert(0, str(tmp_path))
    known_modules = set(sys.modules)
    yield root
    for key in list(sys.modules):
        if key not in known_modules:
            del sys.modules[key]
    sys.path.remove(str(tmp_path))


def _make_local_rules(root, items: dict[str, str]) -> None:
    """Create .py item files under *root*."""
    for item_name, content in items.items():
        (root / (item_name + ".py")).write_text(content)


def _rule_module(name: str = "MyRule") -> str:
    """Return Python source for a module that exposes a RULE GameRule."""
    return (
        "from engine.engine import GameRule\n"
        "class " + name + "(GameRule): pass\n"
        "RULE = " + name + "()\n"
    )


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------


def test_scene_local_registry_items_is_empty_on_construction() -> None:
    registry = SceneLocalRegistry(item_attr="RULE")

    assert registry.items() == []


# ---------------------------------------------------------------------------
# SceneLocalRegistry.scan_dir — self-population
# ---------------------------------------------------------------------------


def test_scan_dir_on_missing_directory_leaves_registry_empty_and_raises_nothing(
    tmp_path,
) -> None:
    registry = SceneLocalRegistry(item_attr="RULE")
    missing = str(tmp_path / "does_not_exist")

    registry.scan_dir(missing, MODULE_PREFIX)  # must not raise

    assert registry.items() == []


def test_scan_dir_on_file_path_leaves_registry_empty(tmp_path) -> None:
    not_a_dir = tmp_path / "file.py"
    not_a_dir.write_text("")
    registry = SceneLocalRegistry(item_attr="RULE")

    registry.scan_dir(str(not_a_dir), MODULE_PREFIX)

    assert registry.items() == []


def test_scan_dir_on_populated_directory_yields_expected_items(local_env) -> None:
    _make_local_rules(local_env, {"alpha": _rule_module("Alpha"), "beta": _rule_module("Beta")})
    registry = SceneLocalRegistry(item_attr="RULE")

    registry.scan_dir(str(local_env), MODULE_PREFIX)

    assert registry.items() == ["alpha", "beta"]


# ---------------------------------------------------------------------------
# SceneLocalRegistry.get — item loading (via scan_dir)
# ---------------------------------------------------------------------------


def test_get_returns_game_rule_for_registered_item_name(local_env) -> None:
    _make_local_rules(local_env, {"my_rule": _rule_module()})
    from engine.engine import GameRule

    registry = SceneLocalRegistry(item_attr="RULE")
    registry.scan_dir(str(local_env), MODULE_PREFIX)

    result = registry.get("my_rule", GameRule)

    assert isinstance(result, GameRule)


def test_get_returns_same_instance_on_repeated_calls(local_env) -> None:
    _make_local_rules(local_env, {"my_rule": _rule_module()})
    from engine.engine import GameRule

    registry = SceneLocalRegistry(item_attr="RULE")
    registry.scan_dir(str(local_env), MODULE_PREFIX)

    first = registry.get("my_rule", GameRule)
    second = registry.get("my_rule", GameRule)

    assert first is second


def test_get_raises_for_unknown_item_name(local_env) -> None:
    registry = SceneLocalRegistry(item_attr="RULE")
    registry.scan_dir(str(local_env), MODULE_PREFIX)
    from engine.engine import GameRule

    with pytest.raises(UnknownItemError) as excinfo:
        registry.get("ghost", GameRule)
    assert excinfo.value.item_name == "ghost"
    assert excinfo.value.pack_name is None
    assert excinfo.value.available == []


def test_get_raises_when_item_module_has_no_rule_attribute(local_env) -> None:
    _make_local_rules(local_env, {"bad_rule": "WRONG_NAME = 1"})
    from engine.engine import GameRule

    registry = SceneLocalRegistry(item_attr="RULE")
    registry.scan_dir(str(local_env), MODULE_PREFIX)

    with pytest.raises(MissingItemAttributeError) as excinfo:
        registry.get("bad_rule", GameRule)
    assert excinfo.value.attr == "RULE"


def test_get_raises_when_rule_attribute_is_not_a_game_rule(local_env) -> None:
    _make_local_rules(local_env, {"bad_rule": "RULE = 'not_a_rule'"})
    from engine.engine import GameRule

    registry = SceneLocalRegistry(item_attr="RULE")
    registry.scan_dir(str(local_env), MODULE_PREFIX)

    with pytest.raises(ItemTypeError) as excinfo:
        registry.get("bad_rule", GameRule)
    assert excinfo.value.expected_class is GameRule


# ---------------------------------------------------------------------------
# SceneLocalRegistry.items — listing
# ---------------------------------------------------------------------------


def test_items_returns_sorted_item_names(local_env) -> None:
    _make_local_rules(
        local_env,
        {
            "zebra": _rule_module("Zebra"),
            "alpha": _rule_module("Alpha"),
            "mango": _rule_module("Mango"),
        },
    )
    registry = SceneLocalRegistry(item_attr="RULE")
    registry.scan_dir(str(local_env), MODULE_PREFIX)

    assert registry.items() == ["alpha", "mango", "zebra"]


# ---------------------------------------------------------------------------
# SceneLocalRegistry — uses __slots__
# ---------------------------------------------------------------------------


def test_scene_local_registry_uses_slots() -> None:
    assert hasattr(SceneLocalRegistry, "__slots__")


def test_scene_local_registry_does_not_allow_arbitrary_attributes() -> None:
    registry = SceneLocalRegistry(item_attr="RULE")

    with pytest.raises(AttributeError):
        registry.unexpected = "oops"  # type: ignore[attr-defined]
