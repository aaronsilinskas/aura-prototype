"""Tests for engine.scene.SceneLocalRegistry.

SceneLocalRegistry maps item name → module for one scene's local rules (or
effects).  It shares its item-loading internals with PackRegistry (no
duplicated import/attr/isinstance/cache logic) but has no version concept.
"""

from __future__ import annotations

import pytest

from engine.engine import GameRule
from engine.pack_catalog import scan_pack_roots
from engine.packs import ItemTypeError, MissingItemAttributeError, UnknownItemError
from engine.scene import SceneLocalRegistry

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _rule_module(name: str = "MyRule") -> str:
    """Return Python source for a module that exposes a RULE GameRule."""
    return (
        "from engine.engine import GameRule\n"
        "class " + name + "(GameRule): pass\n"
        "RULE = " + name + "()\n"
    )


def _local_rules(
    pack_tree, rules: dict[str, str] | None, *, rules_is_a_file: bool = False
) -> SceneLocalRegistry:
    """Scan one scene with local *rules*; return its local rule registry.

    *rules_is_a_file* puts a plain file where the scene's ``rules/`` folder would be.
    """
    root = pack_tree.root("tslr_flash")
    scene_dir = pack_tree.scene(root, "forest", rules=rules)
    if rules_is_a_file:
        (scene_dir / "rules").write_text("")
    return scan_pack_roots([str(root)]).scene_registry.get("forest").local_rule_registry


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------


def test_scene_local_registry_with_no_arguments_is_a_valid_empty_registry() -> None:
    registry = SceneLocalRegistry()

    assert registry.items() == []
    with pytest.raises(UnknownItemError) as excinfo:
        registry.get("anything", object)
    assert excinfo.value.item_name == "anything"


# ---------------------------------------------------------------------------
# Population from the scanned scene's rules/ folder
# ---------------------------------------------------------------------------


def test_a_scene_whose_rules_entry_is_a_file_has_an_empty_local_rule_registry(
    pack_tree,
) -> None:
    registry = _local_rules(pack_tree, None, rules_is_a_file=True)

    assert registry.items() == []


def test_a_populated_rules_folder_yields_its_items(pack_tree) -> None:
    registry = _local_rules(
        pack_tree, {"alpha": _rule_module("Alpha"), "beta": _rule_module("Beta")}
    )

    assert registry.items() == ["alpha", "beta"]


# ---------------------------------------------------------------------------
# SceneLocalRegistry.get — item loading
# ---------------------------------------------------------------------------


def test_get_returns_game_rule_for_registered_item_name(pack_tree) -> None:
    registry = _local_rules(pack_tree, {"my_rule": _rule_module()})

    result = registry.get("my_rule", GameRule)

    assert isinstance(result, GameRule)


def test_get_returns_same_instance_on_repeated_calls(pack_tree) -> None:
    registry = _local_rules(pack_tree, {"my_rule": _rule_module()})

    first = registry.get("my_rule", GameRule)
    second = registry.get("my_rule", GameRule)

    assert first is second


def test_get_raises_for_unknown_item_name(pack_tree) -> None:
    registry = _local_rules(pack_tree, None)

    with pytest.raises(UnknownItemError) as excinfo:
        registry.get("ghost", GameRule)
    assert excinfo.value.item_name == "ghost"
    assert excinfo.value.pack_name is None
    assert excinfo.value.available == []


def test_get_raises_when_item_module_has_no_rule_attribute(pack_tree) -> None:
    registry = _local_rules(pack_tree, {"bad_rule": "WRONG_NAME = 1"})

    with pytest.raises(MissingItemAttributeError) as excinfo:
        registry.get("bad_rule", GameRule)
    assert excinfo.value.attr == "RULE"


def test_get_raises_when_rule_attribute_is_not_a_game_rule(pack_tree) -> None:
    registry = _local_rules(pack_tree, {"bad_rule": "RULE = 'not_a_rule'"})

    with pytest.raises(ItemTypeError) as excinfo:
        registry.get("bad_rule", GameRule)
    assert excinfo.value.expected_class is GameRule


# ---------------------------------------------------------------------------
# SceneLocalRegistry.items — listing
# ---------------------------------------------------------------------------


def test_items_returns_sorted_item_names(pack_tree) -> None:
    registry = _local_rules(
        pack_tree,
        {
            "zebra": _rule_module("Zebra"),
            "alpha": _rule_module("Alpha"),
            "mango": _rule_module("Mango"),
        },
    )

    assert registry.items() == ["alpha", "mango", "zebra"]


# ---------------------------------------------------------------------------
# SceneLocalRegistry — uses __slots__
# ---------------------------------------------------------------------------


def test_scene_local_registry_uses_slots() -> None:
    assert hasattr(SceneLocalRegistry, "__slots__")


def test_scene_local_registry_does_not_allow_arbitrary_attributes() -> None:
    registry = SceneLocalRegistry()

    with pytest.raises(AttributeError):
        registry.unexpected = "oops"  # type: ignore[attr-defined]
