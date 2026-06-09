"""Integration smoke tests: PackRegistry discovers the first-party packs under packs/."""

from __future__ import annotations

import os

import pytest

from effects.effect import EffectConfig
from engine.effects.manager import EffectBuilder
from engine.engine import GameEngine, GameRule
from engine.packs import PackRegistry
from engine.scene import Scene, SceneManager, SceneRegistry
from engine.state import EffectControls
from packs.rules.debug.button_events import ButtonEventsRule
from packs.rules.debug.event_logger import EventLoggerRule

_PACKS_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))


def _packs_path(*parts: str) -> str:
    return os.path.join(_PACKS_ROOT, *parts)


# --- Effects registry ---


def test_fire_pack_exposes_valid_effect_builder() -> None:
    registry = PackRegistry(item_attr="BUILD")
    registry.scan_dir(_packs_path("effects"), "packs.effects")

    builder = registry.get("elements", "fire", EffectBuilder)

    assert isinstance(builder, EffectBuilder)


def test_solid_pack_exposes_valid_effect_builder() -> None:
    registry = PackRegistry(item_attr="BUILD")
    registry.scan_dir(_packs_path("effects"), "packs.effects")

    builder = registry.get("basic", "solid", EffectBuilder)

    assert isinstance(builder, EffectBuilder)


def test_rlgl_scene_local_effect_builders_are_discovered() -> None:
    scene_registry = SceneRegistry()
    scene_registry.scan_dir(_packs_path("scenes"), "packs.scenes")

    scene = scene_registry.get("rlgl")
    local_effects = scene.local_effect_registry

    for effect_name in (
        "red_light_music",
        "green_light_music",
        "warning_sting",
        "game_over_sting",
        "win_sting",
        "level_up",
        "ready",
    ):
        builder = local_effects.get(effect_name, EffectBuilder)
        assert isinstance(builder, EffectBuilder)


def test_rlgl_scene_local_audio_only_effects_have_no_pixels() -> None:
    scene_registry = SceneRegistry()
    scene_registry.scan_dir(_packs_path("scenes"), "packs.scenes")

    scene = scene_registry.get("rlgl")
    local_effects = scene.local_effect_registry

    for effect_name in ("red_light_music", "green_light_music", "game_over_sting", "win_sting"):
        builder = local_effects.get(effect_name, EffectBuilder)
        config = EffectConfig(resolution=16, options={})
        effect = builder(effect_name, config)
        assert effect.pixels is None


def test_rlgl_scene_local_warning_sting_effect_has_pixels() -> None:
    scene_registry = SceneRegistry()
    scene_registry.scan_dir(_packs_path("scenes"), "packs.scenes")

    scene = scene_registry.get("rlgl")
    local_effects = scene.local_effect_registry

    builder = local_effects.get("warning_sting", EffectBuilder)
    config = EffectConfig(resolution=16, options={})
    effect = builder("warning_sting", config)
    assert effect.pixels is not None


def test_rlgl_scene_json_does_not_list_rlgl_effect_or_rule_packs() -> None:
    scene_registry = SceneRegistry()
    scene_registry.scan_dir(_packs_path("scenes"), "packs.scenes")

    scene = scene_registry.get("rlgl")

    pack_names = [name for name, _ in scene.effect_packs]
    assert "rlgl" not in pack_names
    rule_pack_names = [name for name, _ in scene.rule_packs]
    assert "rlgl" not in rule_pack_names


# --- Rules registry ---


def test_button_events_rule_is_a_game_rule() -> None:
    registry = PackRegistry(item_attr="RULE")
    registry.scan_dir(_packs_path("rules"), "packs.rules")

    rule = registry.get("debug", "button_events", GameRule)

    assert isinstance(rule, GameRule)


def test_event_logger_rule_is_a_game_rule() -> None:
    registry = PackRegistry(item_attr="RULE")
    registry.scan_dir(_packs_path("rules"), "packs.rules")

    rule = registry.get("debug", "event_logger", GameRule)

    assert isinstance(rule, GameRule)


def test_debug_exposes_all_expected_rule_modules() -> None:
    rule_registry = PackRegistry(item_attr="RULE")
    rule_registry.scan_dir(_packs_path("rules"), "packs.rules")

    items = rule_registry.items("debug")

    assert "button_events" in items
    assert "event_logger" in items


def test_hw_test_mode_rule_is_a_game_rule() -> None:
    registry = PackRegistry(item_attr="RULE")
    registry.scan_dir(_packs_path("rules"), "packs.rules")

    rule = registry.get("hw_test", "mode_rule", GameRule)

    assert isinstance(rule, GameRule)


def test_hw_test_motion_rule_is_a_game_rule() -> None:
    registry = PackRegistry(item_attr="RULE")
    registry.scan_dir(_packs_path("rules"), "packs.rules")

    rule = registry.get("hw_test", "motion_rule", GameRule)

    assert isinstance(rule, GameRule)


def test_hw_test_network_rule_is_a_game_rule() -> None:
    registry = PackRegistry(item_attr="RULE")
    registry.scan_dir(_packs_path("rules"), "packs.rules")

    rule = registry.get("hw_test", "network_rule", GameRule)

    assert isinstance(rule, GameRule)


def test_hw_test_exposes_all_expected_rule_modules() -> None:
    registry = PackRegistry(item_attr="RULE")
    registry.scan_dir(_packs_path("rules"), "packs.rules")

    items = registry.items("hw_test")

    assert "mode_rule" in items
    assert "motion_rule" in items
    assert "network_rule" in items


# --- SceneManager integration ---


@pytest.fixture
def loaded_debug_engine():
    rule_registry = PackRegistry(item_attr="RULE")
    rule_registry.scan_dir(_packs_path("rules"), "packs.rules")
    effect_registry = PackRegistry(item_attr="BUILD")
    engine = GameEngine(EffectControls())
    scene_registry = SceneRegistry()
    scene_registry.register(
        "test_scene",
        lambda: Scene(effect_packs=[], rule_packs=[("debug", "1.0")]),
    )
    manager = SceneManager(engine, effect_registry, rule_registry, scene_registry)
    manager.load("test_scene")
    manager.update()
    return engine, rule_registry


def test_scene_manager_load_wires_button_events_rule_from_pack(
    loaded_debug_engine,
) -> None:
    engine, _ = loaded_debug_engine

    assert any(isinstance(r, ButtonEventsRule) for r in engine.rules)


def test_scene_manager_load_wires_event_logger_rule_from_pack(
    loaded_debug_engine,
) -> None:
    engine, _ = loaded_debug_engine

    assert any(isinstance(r, EventLoggerRule) for r in engine.rules)


def test_scene_manager_load_activates_all_rules_from_pack(
    loaded_debug_engine,
) -> None:
    engine, rule_registry = loaded_debug_engine

    expected_count = len(rule_registry.items("debug"))

    assert all(isinstance(r, GameRule) for r in engine.rules)
    assert len(engine.rules) == expected_count


def test_scene_manager_load_raises_for_incompatible_pack_version() -> None:
    rule_registry = PackRegistry(item_attr="RULE")
    rule_registry.scan_dir(_packs_path("rules"), "packs.rules")
    effect_registry = PackRegistry(item_attr="BUILD")
    engine = GameEngine(EffectControls())
    scene_registry = SceneRegistry()
    scene_registry.register(
        "test_scene",
        lambda: Scene(effect_packs=[], rule_packs=[("debug", "99.0")]),
    )
    manager = SceneManager(engine, effect_registry, rule_registry, scene_registry)

    with pytest.raises(ValueError):
        manager.load("test_scene")
