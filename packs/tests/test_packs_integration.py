"""Integration smoke tests: PackRegistry discovers the first-party packs under packs/."""

from __future__ import annotations

import os

from engine.engine import GameEngine, GameRule
from engine.packs import PackRegistry
from engine.scene import Scene, SceneManager
from engine.state import EffectControls

_PACKS_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))


def _packs_path(*parts: str) -> str:
    return os.path.join(_PACKS_ROOT, *parts)


def test_scan_effects_discovers_elements_pack() -> None:
    registry = PackRegistry(extractor=lambda module: module)
    registry.scan_dir(_packs_path("effects"), "packs.effects")
    # Verify the elements pack was discovered by attempting to access a known item
    module = registry.get("elements", "fire")
    assert hasattr(module, "build_fire_renderer")


def test_scan_rules_discovers_debug_pack() -> None:
    registry = PackRegistry(extractor=lambda module: module.RULE)
    registry.scan_dir(_packs_path("rules"), "packs.rules")
    rule = registry.get("debug_pack", "button_events")

    assert isinstance(rule, GameRule)


def test_scan_rules_debug_pack_event_logger_exports_rule() -> None:
    registry = PackRegistry(extractor=lambda module: module.RULE)
    registry.scan_dir(_packs_path("rules"), "packs.rules")
    rule = registry.get("debug_pack", "event_logger")

    assert isinstance(rule, GameRule)


def test_debug_pack_items_discovered_via_registry_items() -> None:
    rule_registry = PackRegistry(extractor=lambda m: m.RULE)
    rule_registry.scan_dir(_packs_path("rules"), "packs.rules")

    items = rule_registry.items("debug_pack")

    assert "button_events" in items
    assert "event_logger" in items


def test_scene_manager_load_with_debug_pack_wires_button_events_rule() -> None:
    rule_registry = PackRegistry(extractor=lambda m: m.RULE)
    rule_registry.scan_dir(_packs_path("rules"), "packs.rules")
    effect_registry = PackRegistry(extractor=lambda m: m.BUILD)
    engine = GameEngine(EffectControls())
    manager = SceneManager(engine, effect_registry, rule_registry)

    manager.register(
        "test_scene",
        lambda: Scene(rules=[], effect_packs=[], rule_packs=[("debug_pack", "1.0")]),
    )
    manager.load("test_scene")
    manager.update()  # applies the deferred load transition

    rule_names = {r.name for r in engine._rules}
    assert "debug.button_event" in rule_names


def test_scene_manager_load_with_debug_pack_wires_event_logger_rule() -> None:
    rule_registry = PackRegistry(extractor=lambda m: m.RULE)
    rule_registry.scan_dir(_packs_path("rules"), "packs.rules")
    effect_registry = PackRegistry(extractor=lambda m: m.BUILD)
    engine = GameEngine(EffectControls())
    manager = SceneManager(engine, effect_registry, rule_registry)

    manager.register(
        "test_scene",
        lambda: Scene(rules=[], effect_packs=[], rule_packs=[("debug_pack", "1.0")]),
    )
    manager.load("test_scene")
    manager.update()  # applies the deferred load transition

    rule_names = {r.name for r in engine._rules}
    assert "debug.event_logger" in rule_names


def test_scene_manager_load_with_debug_pack_wires_all_rules_in_combined_rules() -> None:
    rule_registry = PackRegistry(extractor=lambda m: m.RULE)
    rule_registry.scan_dir(_packs_path("rules"), "packs.rules")
    effect_registry = PackRegistry(extractor=lambda m: m.BUILD)
    engine = GameEngine(EffectControls())
    manager = SceneManager(engine, effect_registry, rule_registry)

    manager.register(
        "test_scene",
        lambda: Scene(rules=[], effect_packs=[], rule_packs=[("debug_pack", "1.0")]),
    )
    manager.load("test_scene")
    manager.update()  # applies the deferred load transition

    assert all(isinstance(r, GameRule) for r in engine._rules)
    assert len(engine._rules) == 2
