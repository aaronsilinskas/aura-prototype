"""Tests for scene-local rule discovery through ``scan_pack_roots`` (the rules/
subdir of each scanned scene) and SceneManager rule resolution with scene-local rules.
"""

from __future__ import annotations

import pytest

from engine.engine import GameEngine, GameRule
from engine.events import Event, EventGroup
from engine.pack_catalog import scan_pack_roots
from engine.scene import Scene
from engine.tests.helpers import (
    SpyEffectControls,
    make_scene_manager,
    rule_source,
)

_GROUP = EventGroup("test")


def _make_engine() -> GameEngine:
    return GameEngine(effect_controls=SpyEffectControls())


# ---------------------------------------------------------------------------
# rules/ folder discovery
# ---------------------------------------------------------------------------


def test_a_scenes_rules_folder_items_are_its_local_rules(pack_tree) -> None:
    registry = pack_tree.scan(
        scenes={"forest": {"rules": {"ambush": rule_source("Ambush")}}}
    ).scene_registry

    scene = registry.get("forest")
    assert "ambush" in scene.local_rule_registry.items()


def test_scene_constructed_directly_has_empty_local_rule_registry() -> None:
    scene = Scene(effect_packs=[], rule_packs=[])

    assert scene.local_rule_registry.items() == []


def test_each_fresh_scene_shares_one_local_rule_registry(pack_tree) -> None:
    registry = pack_tree.scan(
        scenes={"forest": {"rules": {"my_rule": rule_source()}}}
    ).scene_registry

    scene_a = registry.get("forest")
    scene_b = registry.get("forest")

    assert scene_a.local_rule_registry is scene_b.local_rule_registry


def test_a_scenes_local_rules_are_not_visible_to_another_scene(pack_tree) -> None:
    registry = pack_tree.scan(
        scenes={"forest": {"rules": {"secret_rule": rule_source()}}, "cave": {}}
    ).scene_registry

    cave_scene = registry.get("cave")
    assert "secret_rule" not in cave_scene.local_rule_registry.items()


# ---------------------------------------------------------------------------
# SceneManager — scene-local rules appended after pack rules on load
# ---------------------------------------------------------------------------


def test_scene_manager_load_includes_scene_local_rules_in_engine(pack_tree) -> None:
    catalog = pack_tree.scan(scenes={"my_scene": {"rules": {"local_rule": rule_source()}}})

    engine = _make_engine()
    manager = make_scene_manager(catalog, engine=engine)
    manager.load("my_scene")
    manager.update()

    assert len(engine.rules) == 1
    assert isinstance(engine.rules[0], GameRule)


def test_scene_manager_load_appends_local_rules_after_pack_rules(pack_tree) -> None:
    root = pack_tree.root("ts_flash")
    pack_tree.rule_pack(root, "pack_rules", items={"pack_rule": rule_source("PackRule")})
    pack_tree.scene(
        root,
        "my_scene",
        rule_packs=[["pack_rules", "1.0"]],
        rules={"local_rule": rule_source("LocalRule")},
    )
    catalog = scan_pack_roots([str(root)])
    pack_rule = catalog.rule_registry.get("pack_rules", "pack_rule", GameRule)

    engine = _make_engine()
    manager = make_scene_manager(catalog, engine=engine)
    manager.load("my_scene")
    manager.update()

    rules = engine.rules
    assert len(rules) == 2
    assert rules[0] is pack_rule
    assert isinstance(rules[1], GameRule)
    assert rules[1] is not pack_rule


def test_a_local_rule_without_a_rule_attribute_fails_when_the_scene_load_is_applied(
    pack_tree,
) -> None:
    catalog = pack_tree.scan(scenes={"my_scene": {"rules": {"broken_rule": "NOT_A_RULE = 1"}}})

    manager = make_scene_manager(catalog)
    manager.load("my_scene")

    with pytest.raises(ValueError, match="no attribute 'RULE'"):
        manager.update()


def test_scene_manager_local_rules_are_not_active_for_other_loaded_scene(pack_tree) -> None:
    catalog = pack_tree.scan(
        scenes={"scene_a": {"rules": {"local_rule": rule_source()}}, "scene_b": {}}
    )

    engine = _make_engine()
    manager = make_scene_manager(catalog, engine=engine)
    manager.load("scene_b")
    manager.update()

    assert engine.rules == []


def test_local_rule_receives_events_after_scene_load(pack_tree) -> None:
    rule_src = (
        "from engine.engine import GameRule\n"
        "from engine.state import GameState\n"
        "from engine.events import Event\n"
        "\n"
        "class RecorderRule(GameRule):\n"
        "    def __init__(self):\n"
        "        self.received = []\n"
        "        self.on(Event, self._handle)\n"
        "    def _handle(self, event, state):\n"
        "        self.received.append(event.name)\n"
        "\n"
        "RULE = RecorderRule()\n"
    )
    catalog = pack_tree.scan(scenes={"my_scene": {"rules": {"recorder": rule_src}}})

    engine = _make_engine()
    manager = make_scene_manager(catalog, engine=engine)
    manager.load("my_scene")
    manager.update()
    manager.update()  # first engine tick

    manager.active_state.queue_event(Event(_GROUP, "ping"))
    manager.update()

    rule = engine.rules[0]
    assert "ping" in rule.received
