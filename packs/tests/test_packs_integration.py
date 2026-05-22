"""Integration smoke tests: PackRegistry discovers the first-party packs under packs/."""

from __future__ import annotations

import os

import pytest

from engine.engine import GameEngine, GameRule
from engine.packs import PackRegistry
from engine.scene import Scene, SceneManager
from engine.state import EffectControls

_PACKS_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))


def _packs_path(*parts: str) -> str:
    return os.path.join(_PACKS_ROOT, *parts)


# --- Effects registry ---


def test_fire_module_is_accessible_via_effects_registry() -> None:
    registry = PackRegistry(extractor=lambda module: module)
    registry.scan_dir(_packs_path("effects"), "packs.effects")

    module = registry.get("elements", "fire")

    assert hasattr(module, "build_fire_renderer")


# --- Rules registry ---


def test_button_events_rule_is_a_game_rule() -> None:
    registry = PackRegistry(extractor=lambda module: module.RULE)
    registry.scan_dir(_packs_path("rules"), "packs.rules")

    rule = registry.get("debug", "button_events")

    assert isinstance(rule, GameRule)


def test_event_logger_rule_is_a_game_rule() -> None:
    registry = PackRegistry(extractor=lambda module: module.RULE)
    registry.scan_dir(_packs_path("rules"), "packs.rules")

    rule = registry.get("debug", "event_logger")

    assert isinstance(rule, GameRule)


def test_debug_exposes_all_expected_rule_modules() -> None:
    rule_registry = PackRegistry(extractor=lambda m: m.RULE)
    rule_registry.scan_dir(_packs_path("rules"), "packs.rules")

    items = rule_registry.items("debug")

    assert "button_events" in items
    assert "event_logger" in items


# --- SceneManager integration ---


@pytest.fixture
def loaded_debug_engine():
    rule_registry = PackRegistry(extractor=lambda m: m.RULE)
    rule_registry.scan_dir(_packs_path("rules"), "packs.rules")
    effect_registry = PackRegistry(extractor=lambda m: m.BUILD)
    engine = GameEngine(EffectControls())
    manager = SceneManager(engine, effect_registry, rule_registry)
    manager.register(
        "test_scene",
        lambda: Scene(rules=[], effect_packs=[], rule_packs=[("debug", "1.0")]),
    )
    manager.load("test_scene")
    manager.update()
    return engine, rule_registry


def test_scene_manager_load_wires_button_events_rule_from_pack(
    loaded_debug_engine,
) -> None:
    engine, _ = loaded_debug_engine

    rule_names = {r.name for r in engine._rules}

    assert "debug.button_event" in rule_names


def test_scene_manager_load_wires_event_logger_rule_from_pack(
    loaded_debug_engine,
) -> None:
    engine, _ = loaded_debug_engine

    rule_names = {r.name for r in engine._rules}

    assert "debug.event_logger" in rule_names


def test_scene_manager_load_activates_all_rules_from_pack(
    loaded_debug_engine,
) -> None:
    engine, rule_registry = loaded_debug_engine

    expected_count = len(rule_registry.items("debug"))

    assert all(isinstance(r, GameRule) for r in engine._rules)
    assert len(engine._rules) == expected_count


def test_scene_manager_load_raises_for_incompatible_pack_version() -> None:
    rule_registry = PackRegistry(extractor=lambda m: m.RULE)
    rule_registry.scan_dir(_packs_path("rules"), "packs.rules")
    effect_registry = PackRegistry(extractor=lambda m: m.BUILD)
    engine = GameEngine(EffectControls())
    manager = SceneManager(engine, effect_registry, rule_registry)
    manager.register(
        "test_scene",
        lambda: Scene(rules=[], effect_packs=[], rule_packs=[("debug", "99.0")]),
    )

    with pytest.raises(ValueError):
        manager.load("test_scene")
