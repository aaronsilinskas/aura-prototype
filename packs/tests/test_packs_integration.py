"""Integration smoke tests: PackRegistry discovers the first-party packs under packs/."""

from __future__ import annotations

import os

import pytest

from effects.effect import EffectConfig
from engine.audio import AudioRegistry
from engine.effects.manager import EffectBuilder, EffectManager
from engine.engine import GameEngine, GameRule
from engine.packs import PackRegistry
from engine.scene import Scene, SceneManager, SceneRegistry
from engine.state import SceneReboot
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


def test_red_light_green_light_scene_local_effect_builders_are_discovered() -> None:
    scene_registry = SceneRegistry()
    scene_registry.scan_dir(_packs_path("scenes"), "packs.scenes")

    scene = scene_registry.get("red_light_green_light")
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


def test_red_light_green_light_scene_local_audio_only_effects_have_no_pixels() -> None:
    scene_registry = SceneRegistry()
    scene_registry.scan_dir(_packs_path("scenes"), "packs.scenes")

    scene = scene_registry.get("red_light_green_light")
    local_effects = scene.local_effect_registry

    for effect_name in ("red_light_music", "green_light_music", "game_over_sting", "win_sting"):
        builder = local_effects.get(effect_name, EffectBuilder)
        config = EffectConfig(resolution=16, options={})
        effect = builder(effect_name, config)
        assert effect.pixels is None


def test_red_light_green_light_scene_local_warning_sting_effect_has_pixels() -> None:
    scene_registry = SceneRegistry()
    scene_registry.scan_dir(_packs_path("scenes"), "packs.scenes")

    scene = scene_registry.get("red_light_green_light")
    local_effects = scene.local_effect_registry

    builder = local_effects.get("warning_sting", EffectBuilder)
    config = EffectConfig(resolution=16, options={})
    effect = builder("warning_sting", config)
    assert effect.pixels is not None


def test_red_light_green_light_scene_json_does_not_list_own_effect_or_rule_packs() -> None:
    scene_registry = SceneRegistry()
    scene_registry.scan_dir(_packs_path("scenes"), "packs.scenes")

    scene = scene_registry.get("red_light_green_light")

    pack_names = [name for name, _ in scene.effect_packs]
    assert "red_light_green_light" not in pack_names
    rule_pack_names = [name for name, _ in scene.rule_packs]
    assert "red_light_green_light" not in rule_pack_names


# --- Rules registry ---


def test_event_logger_rule_is_a_game_rule() -> None:
    registry = PackRegistry(item_attr="RULE")
    registry.scan_dir(_packs_path("rules"), "packs.rules")

    rule = registry.get("debug", "event_logger", GameRule)

    assert isinstance(rule, GameRule)


def test_debug_exposes_all_expected_rule_modules() -> None:
    rule_registry = PackRegistry(item_attr="RULE")
    rule_registry.scan_dir(_packs_path("rules"), "packs.rules")

    items = rule_registry.items("debug")

    assert "event_logger" in items


# --- Return-to-lobby rule pack (issue #912) ---


def test_return_to_lobby_rule_is_a_game_rule() -> None:
    registry = PackRegistry(item_attr="RULE")
    registry.scan_dir(_packs_path("rules"), "packs.rules")

    rule = registry.get("return_to_lobby", "return_to_lobby_rule", GameRule)

    assert isinstance(rule, GameRule)


@pytest.mark.parametrize(
    "scene_name", ["hardware_test", "element_browser", "red_light_green_light", "tag"]
)
def test_non_lobby_scene_declares_the_return_to_lobby_rule_pack(scene_name: str) -> None:
    scene_registry = SceneRegistry()
    scene_registry.scan_dir(_packs_path("scenes"), "packs.scenes")

    scene = scene_registry.get(scene_name)

    rule_pack_names = [tuple(entry) for entry in scene.rule_packs]
    assert ("return_to_lobby", "1.0") in rule_pack_names


@pytest.mark.parametrize(
    "scene_name", ["hardware_test", "element_browser", "red_light_green_light", "tag"]
)
def test_non_lobby_scene_configures_return_to_lobby_hold_seconds(scene_name: str) -> None:
    scene_registry = SceneRegistry()
    scene_registry.scan_dir(_packs_path("scenes"), "packs.scenes")

    scene = scene_registry.get(scene_name)

    assert scene.initial_data["return_to_lobby"] == {"hold_seconds": 5.0}


# --- ir_range_receiver scene discovery (issue #918) ---


def test_ir_range_receiver_scene_local_rule_is_discovered() -> None:
    scene_registry = SceneRegistry()
    scene_registry.scan_dir(_packs_path("scenes"), "packs.scenes")

    scene = scene_registry.get("ir_range_receiver")
    local_rules = scene.local_rule_registry

    rule = local_rules.get("receiver_rule", GameRule)
    assert isinstance(rule, GameRule)


def test_ir_range_receiver_scene_declares_the_basic_effect_pack() -> None:
    scene_registry = SceneRegistry()
    scene_registry.scan_dir(_packs_path("scenes"), "packs.scenes")

    scene = scene_registry.get("ir_range_receiver")

    pack_names = [name for name, _ in scene.effect_packs]
    assert "basic" in pack_names


def test_ir_range_receiver_scene_declares_no_return_to_lobby_rule_pack() -> None:
    """Minimal bench scene -- no phases, no buttons, no return_to_lobby."""
    scene_registry = SceneRegistry()
    scene_registry.scan_dir(_packs_path("scenes"), "packs.scenes")

    scene = scene_registry.get("ir_range_receiver")

    rule_pack_names = [name for name, _ in scene.rule_packs]
    assert rule_pack_names == []


def test_hardware_test_scene_local_effect_sfx_test_is_discovered() -> None:
    scene_registry = SceneRegistry()
    scene_registry.scan_dir(_packs_path("scenes"), "packs.scenes")

    scene = scene_registry.get("hardware_test")
    local_effects = scene.local_effect_registry

    builder = local_effects.get("sfx_test", EffectBuilder)
    assert isinstance(builder, EffectBuilder)


def test_hardware_test_scene_local_sfx_test_produces_no_pixels() -> None:
    scene_registry = SceneRegistry()
    scene_registry.scan_dir(_packs_path("scenes"), "packs.scenes")

    scene = scene_registry.get("hardware_test")
    local_effects = scene.local_effect_registry

    builder = local_effects.get("sfx_test", EffectBuilder)
    config = EffectConfig(resolution=16, options={})
    effect = builder("sfx_test", config)
    assert effect.pixels is None


def test_hardware_test_scene_local_rules_are_discovered() -> None:
    scene_registry = SceneRegistry()
    scene_registry.scan_dir(_packs_path("scenes"), "packs.scenes")

    scene = scene_registry.get("hardware_test")
    local_rules = scene.local_rule_registry

    for rule_name in ("rgb_rule", "motion_rule", "ir_rule", "radio_rule", "sfx_rule"):
        rule = local_rules.get(rule_name, GameRule)
        assert isinstance(rule, GameRule), f"{rule_name} expected to be a GameRule"


def test_hardware_test_scene_json_does_not_list_own_effect_pack() -> None:
    scene_registry = SceneRegistry()
    scene_registry.scan_dir(_packs_path("scenes"), "packs.scenes")

    scene = scene_registry.get("hardware_test")

    pack_names = [name for name, _ in scene.effect_packs]
    assert "hardware_test" not in pack_names


def test_hardware_test_scene_json_does_not_list_own_rule_pack() -> None:
    scene_registry = SceneRegistry()
    scene_registry.scan_dir(_packs_path("scenes"), "packs.scenes")

    scene = scene_registry.get("hardware_test")

    rule_pack_names = [name for name, _ in scene.rule_packs]
    assert "hardware_test" not in rule_pack_names


def test_hardware_test_scene_json_does_not_list_debug_rule_pack() -> None:
    scene_registry = SceneRegistry()
    scene_registry.scan_dir(_packs_path("scenes"), "packs.scenes")

    scene = scene_registry.get("hardware_test")

    rule_pack_names = [name for name, _ in scene.rule_packs]
    assert "debug" not in rule_pack_names


# --- Tag scene audio discovery (issue #805) ---


def test_tag_scene_every_audio_playing_effects_clip_name_resolves() -> None:
    """Every tag effect that plays audio names a clip AudioRegistry can resolve --
    the shared basic sting via the base, everything else via tag's own sounds/
    overlay -- so the scene can run end-to-end with no unresolved clip."""
    scene_registry = SceneRegistry()
    scene_registry.scan_dir(_packs_path("scenes"), "packs.scenes")
    scene = scene_registry.get("tag")
    local_effects = scene.local_effect_registry

    audio_registry = AudioRegistry()
    audio_registry.scan_pack_sounds("basic", _packs_path("effects", "basic", "sounds"))
    audio_registry.set_scene_sounds(scene.local_sound_map)
    audio_registry.set_allowed_packs(frozenset(name for name, _ in scene.effect_packs))

    resolved_clip_names = []
    for effect_name in local_effects.items():
        builder = local_effects.get(effect_name, EffectBuilder)
        effect = builder(effect_name, EffectConfig(resolution=16, options={}))
        if effect.audio is None:
            continue
        for clip in effect.audio.clips.values():
            resolved_clip_names.append(audio_registry.path(clip.name))

    # Sanity check that the walk actually reached tag's audio-playing effects,
    # so a future scan/discovery regression collapsing this to zero effects
    # doesn't pass silently.
    assert len(resolved_clip_names) == 9


# --- Red Light Green Light scene audio discovery (issue #806) ---


def test_red_light_green_light_scene_every_audio_playing_effects_clip_name_resolves() -> None:
    """Every rlgl effect that plays audio names a clip AudioRegistry can resolve --
    the shared basic sting via the base, everything else via rlgl's own sounds/
    overlay -- so the scene can run end-to-end with no unresolved clip."""
    scene_registry = SceneRegistry()
    scene_registry.scan_dir(_packs_path("scenes"), "packs.scenes")
    scene = scene_registry.get("red_light_green_light")
    local_effects = scene.local_effect_registry

    audio_registry = AudioRegistry()
    audio_registry.scan_pack_sounds("basic", _packs_path("effects", "basic", "sounds"))
    audio_registry.set_scene_sounds(scene.local_sound_map)
    audio_registry.set_allowed_packs(frozenset(name for name, _ in scene.effect_packs))

    resolved_clip_names = []
    for effect_name in local_effects.items():
        builder = local_effects.get(effect_name, EffectBuilder)
        effect = builder(effect_name, EffectConfig(resolution=16, options={}))
        if effect.audio is None:
            continue
        for clip in effect.audio.clips.values():
            resolved_clip_names.append(audio_registry.path(clip.name))

    # Sanity check that the walk actually reached rlgl's audio-playing effects,
    # so a future scan/discovery regression collapsing this to zero effects
    # doesn't pass silently.
    assert len(resolved_clip_names) == 7


# --- SceneManager integration ---


@pytest.fixture
def loaded_debug_engine():
    rule_registry = PackRegistry(item_attr="RULE")
    rule_registry.scan_dir(_packs_path("rules"), "packs.rules")
    effect_registry = PackRegistry(item_attr="BUILD")
    effect_manager = EffectManager(registry=effect_registry, outputs=[])
    engine = GameEngine(effect_manager)
    scene_registry = SceneRegistry()
    scene_registry.register(
        "test_scene",
        lambda: Scene(effect_packs=[], rule_packs=[("debug", "1.0")]),
    )
    manager = SceneManager(
        engine,
        effect_registry,
        rule_registry,
        scene_registry,
        effect_admin=effect_manager,
        audio_overlay_admin=AudioRegistry(),
        scene_reboot=SceneReboot(),
    )
    manager.load("test_scene")
    manager.update()
    return engine, rule_registry


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
    effect_manager = EffectManager(registry=effect_registry, outputs=[])
    engine = GameEngine(effect_manager)
    scene_registry = SceneRegistry()
    scene_registry.register(
        "test_scene",
        lambda: Scene(effect_packs=[], rule_packs=[("debug", "99.0")]),
    )
    manager = SceneManager(
        engine,
        effect_registry,
        rule_registry,
        scene_registry,
        effect_admin=effect_manager,
        audio_overlay_admin=AudioRegistry(),
        scene_reboot=SceneReboot(),
    )

    with pytest.raises(ValueError):
        manager.load("test_scene")
