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
from engine.tests.helpers import rule_source

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _local_rules(pack_tree, rules: dict[str, str] | None) -> SceneLocalRegistry:
    """Scan one scene with local *rules*; return its local rule registry."""
    catalog = pack_tree.scan(scenes={"forest": {"rules": rules}})
    return catalog.scene_registry.get("forest").local_rule_registry


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
    root = pack_tree.root("ts_flash")
    scene_dir = pack_tree.scene(root, "forest")
    (scene_dir / "rules").write_text("")

    scene = scan_pack_roots([str(root)]).scene_registry.get("forest")

    assert scene.local_rule_registry.items() == []


def test_a_populated_rules_folder_yields_its_items(pack_tree) -> None:
    registry = _local_rules(pack_tree, {"alpha": rule_source("Alpha"), "beta": rule_source("Beta")})

    assert registry.items() == ["alpha", "beta"]


# ---------------------------------------------------------------------------
# SceneLocalRegistry.get — item loading
# ---------------------------------------------------------------------------


def test_get_returns_game_rule_for_registered_item_name(pack_tree) -> None:
    registry = _local_rules(pack_tree, {"my_rule": rule_source()})

    result = registry.get("my_rule", GameRule)

    assert isinstance(result, GameRule)


def test_get_returns_same_instance_on_repeated_calls(pack_tree) -> None:
    registry = _local_rules(pack_tree, {"my_rule": rule_source()})

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
            "zebra": rule_source("Zebra"),
            "alpha": rule_source("Alpha"),
            "mango": rule_source("Mango"),
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
