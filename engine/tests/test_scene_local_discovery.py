"""Tests for scene-local rule discovery through ``scan_pack_roots`` (the rules/
subdir of each scanned scene) and a booted scene running its scene-local rules.
"""

from __future__ import annotations

import pytest

from engine.engine import GameRule
from engine.events import Event, EventGroup
from engine.pack_catalog import PackCatalog, scan_pack_roots
from engine.scene_runtime import SceneRuntime
from engine.tests.helpers import make_scene, make_scene_runtime, rule_source

_PING = Event(EventGroup("test"), "ping")


# ---------------------------------------------------------------------------
# rules/ folder discovery
# ---------------------------------------------------------------------------


def test_a_scenes_rules_folder_items_are_its_local_rules(pack_tree) -> None:
    registry = pack_tree.scan(
        scenes={"forest": {"rules": {"ambush": rule_source("Ambush")}}}
    ).scene_registry

    scene = registry.get("forest")
    assert "ambush" in scene.local_rule_registry.items()


def test_a_scene_built_in_memory_has_an_empty_local_rule_registry() -> None:
    scene = make_scene()

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
# The boot scene runs its scene-local rules, after its pack rules
# ---------------------------------------------------------------------------


def _local_rule(catalog: PackCatalog, scene_name: str, item_name: str) -> GameRule:
    """The scene-local rule *item_name* of *scene_name*, the same instance the scene runs."""
    return catalog.scene_registry.get(scene_name).local_rule_registry.get(item_name, GameRule)


def _ping_and_update(runtime: SceneRuntime) -> None:
    runtime.advance_clock()
    runtime.queue_event(_PING)
    runtime.update()


def test_a_boot_scenes_local_rules_hear_its_events(pack_tree) -> None:
    catalog = pack_tree.scan(scenes={"my_scene": {"rules": {"local_rule": rule_source()}}})
    heard: list[Event] = []
    _local_rule(catalog, "my_scene", "local_rule").on(Event, lambda e, state: heard.append(e))
    runtime = make_scene_runtime(catalog)
    runtime.activate_boot_scene("my_scene")

    _ping_and_update(runtime)

    assert heard == [_PING]


def test_a_boot_scenes_local_rules_hear_each_event_after_its_pack_rules(pack_tree) -> None:
    root = pack_tree.root("ts_flash")
    pack_tree.rule_pack(root, "pack_rules", items={"pack_rule": rule_source("PackRule")})
    pack_tree.scene(
        root,
        "my_scene",
        rule_packs=[{"name": "pack_rules", "version": "1.0"}],
        rules={"local_rule": rule_source("LocalRule")},
    )
    catalog = scan_pack_roots([str(root)])
    heard: list[str] = []
    pack_rule = catalog.rule_registry.get("pack_rules", "pack_rule", GameRule)
    pack_rule.on(Event, lambda e, state: heard.append("pack"))
    _local_rule(catalog, "my_scene", "local_rule").on(Event, lambda e, state: heard.append("local"))
    runtime = make_scene_runtime(catalog)
    runtime.activate_boot_scene("my_scene")

    _ping_and_update(runtime)

    assert heard == ["pack", "local"]


def test_a_local_rule_without_a_rule_attribute_fails_when_the_boot_scene_is_activated(
    pack_tree,
) -> None:
    catalog = pack_tree.scan(scenes={"my_scene": {"rules": {"broken_rule": "NOT_A_RULE = 1"}}})
    runtime = make_scene_runtime(catalog)

    with pytest.raises(ValueError, match="no attribute 'RULE'"):
        runtime.activate_boot_scene("my_scene")


def test_a_scenes_local_rules_do_not_hear_another_boot_scenes_events(pack_tree) -> None:
    catalog = pack_tree.scan(
        scenes={"scene_a": {"rules": {"local_rule": rule_source()}}, "scene_b": {}}
    )
    heard: list[Event] = []
    _local_rule(catalog, "scene_a", "local_rule").on(Event, lambda e, state: heard.append(e))
    runtime = make_scene_runtime(catalog)
    runtime.activate_boot_scene("scene_b")

    _ping_and_update(runtime)

    assert heard == []
