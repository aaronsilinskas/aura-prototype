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


def test_fire_pack_exposes_valid_effect_builder() -> None:
    from engine.effects.manager import EffectBuilder

    registry = PackRegistry(item_attr="BUILD")
    registry.scan_dir(_packs_path("effects"), "packs.effects")

    builder = registry.get("elements", "fire", EffectBuilder)

    assert isinstance(builder, EffectBuilder)


def test_solid_pack_exposes_valid_effect_builder() -> None:
    from engine.effects.manager import EffectBuilder

    registry = PackRegistry(item_attr="BUILD")
    registry.scan_dir(_packs_path("effects"), "packs.effects")

    builder = registry.get("basic", "solid", EffectBuilder)

    assert isinstance(builder, EffectBuilder)


def test_rlgl_pack_exposes_valid_effect_builders() -> None:
    from engine.effects.manager import EffectBuilder

    registry = PackRegistry(item_attr="BUILD")
    registry.scan_dir(_packs_path("effects"), "packs.effects")

    for effect_name in ("red_light_music", "green_light_music", "warning_sting", "game_over_sting"):
        builder = registry.get("rlgl", effect_name, EffectBuilder)
        assert isinstance(builder, EffectBuilder)


def test_rlgl_renderers_have_renders_pixels_false() -> None:
    from effects.render import RendererConfig
    from engine.effects.manager import EffectBuilder

    registry = PackRegistry(item_attr="BUILD")
    registry.scan_dir(_packs_path("effects"), "packs.effects")

    for effect_name in ("red_light_music", "green_light_music", "warning_sting", "game_over_sting"):
        builder = registry.get("rlgl", effect_name, EffectBuilder)
        config = RendererConfig(level=5, resolution=16, options={})
        renderer = builder(effect_name, config)
        assert not renderer.renders_pixels


def test_rlgl_sound_path_returns_wav_path() -> None:
    registry = PackRegistry(item_attr="BUILD")
    registry.scan_dir(_packs_path("effects"), "packs.effects")

    path = registry.sound_path("rlgl", "red_light_music")

    assert path is not None
    assert path.endswith("/sounds/red_light_music.wav")


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
    manager = SceneManager(engine, effect_registry, rule_registry)
    manager.register(
        "test_scene",
        lambda: Scene(effect_packs=[], rule_packs=[("debug", "1.0")]),
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
    rule_registry = PackRegistry(item_attr="RULE")
    rule_registry.scan_dir(_packs_path("rules"), "packs.rules")
    effect_registry = PackRegistry(item_attr="BUILD")
    engine = GameEngine(EffectControls())
    manager = SceneManager(engine, effect_registry, rule_registry)
    manager.register(
        "test_scene",
        lambda: Scene(effect_packs=[], rule_packs=[("debug", "99.0")]),
    )

    with pytest.raises(ValueError):
        manager.load("test_scene")
