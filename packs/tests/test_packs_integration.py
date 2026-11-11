"""Integration smoke tests: the pack catalog discovers the first-party packs under packs/."""

from __future__ import annotations

import os

import pytest

from effects.effect import EffectConfig
from engine.effects.builder import EffectBuilder
from engine.effects.manager import EffectManager
from engine.engine import GameEngine, GameRule
from engine.namespace import ActiveSceneNamespace
from engine.pack_catalog import PackCatalog, scan_pack_roots
from engine.scene import PackReference, Scene, SceneManager, SceneRegistry
from engine.state import SceneReboot, Scope
from engine.version import Version
from packs.rules.debug.event_logger import EventLoggerRule

_PACKS_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))


def _under_packs(relative_path: str) -> str:
    """*relative_path*, a path under ``packs/``, where the scanned catalog records it."""
    return os.path.join(_PACKS_ROOT, relative_path)


@pytest.fixture(scope="module")
def catalog() -> PackCatalog:
    """The real ``packs/`` tree scanned the way the device scans its flash root."""
    return scan_pack_roots([_PACKS_ROOT])


# --- Effects registry ---


def test_fire_pack_exposes_valid_effect_builder(catalog: PackCatalog) -> None:
    registry = catalog.effect_registry

    builder = registry.get("elements", "fire", EffectBuilder)

    assert isinstance(builder, EffectBuilder)


def test_solid_pack_exposes_valid_effect_builder(catalog: PackCatalog) -> None:
    registry = catalog.effect_registry

    builder = registry.get("basic", "solid", EffectBuilder)

    assert isinstance(builder, EffectBuilder)


def test_red_light_green_light_scene_local_effect_builders_are_discovered(
    catalog: PackCatalog,
) -> None:
    scene_registry = catalog.scene_registry

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


def test_red_light_green_light_scene_local_audio_only_effects_have_no_pixels(
    catalog: PackCatalog,
) -> None:
    scene_registry = catalog.scene_registry

    scene = scene_registry.get("red_light_green_light")
    local_effects = scene.local_effect_registry

    for effect_name in ("red_light_music", "green_light_music", "game_over_sting", "win_sting"):
        builder = local_effects.get(effect_name, EffectBuilder)
        config = EffectConfig(resolution=16, options={})
        effect = builder(effect_name, config)
        assert effect.pixels is None


def test_red_light_green_light_scene_local_warning_sting_effect_has_pixels(
    catalog: PackCatalog,
) -> None:
    scene_registry = catalog.scene_registry

    scene = scene_registry.get("red_light_green_light")
    local_effects = scene.local_effect_registry

    builder = local_effects.get("warning_sting", EffectBuilder)
    config = EffectConfig(resolution=16, options={})
    effect = builder("warning_sting", config)
    assert effect.pixels is not None


def test_red_light_green_light_scene_json_does_not_list_own_effect_or_rule_packs(
    catalog: PackCatalog,
) -> None:
    scene_registry = catalog.scene_registry

    scene = scene_registry.get("red_light_green_light")

    pack_names = [pack.name for pack in scene.effect_packs]
    assert "red_light_green_light" not in pack_names
    rule_pack_names = [pack.name for pack in scene.rule_packs]
    assert "red_light_green_light" not in rule_pack_names


# --- Rules registry ---


def test_event_logger_rule_is_a_game_rule(catalog: PackCatalog) -> None:
    registry = catalog.rule_registry

    rule = registry.get("debug", "event_logger", GameRule)

    assert isinstance(rule, GameRule)


def test_debug_exposes_all_expected_rule_modules(catalog: PackCatalog) -> None:
    rule_registry = catalog.rule_registry

    items = rule_registry.items("debug")

    assert "event_logger" in items


# --- Return-to-lobby rule pack (issue #912) ---


def test_return_to_lobby_rule_is_a_game_rule(catalog: PackCatalog) -> None:
    registry = catalog.rule_registry

    rule = registry.get("return_to_lobby", "return_to_lobby_rule", GameRule)

    assert isinstance(rule, GameRule)


@pytest.mark.parametrize(
    "scene_name", ["hardware_test", "element_browser", "red_light_green_light", "tag"]
)
def test_non_lobby_scene_declares_the_return_to_lobby_rule_pack(
    scene_name: str, catalog: PackCatalog
) -> None:
    scene_registry = catalog.scene_registry

    scene = scene_registry.get(scene_name)

    rule_pack_names = [pack.name for pack in scene.rule_packs]
    assert "return_to_lobby" in rule_pack_names


@pytest.mark.parametrize(
    "scene_name", ["hardware_test", "element_browser", "red_light_green_light", "tag"]
)
def test_non_lobby_scene_holds_five_seconds_to_return_to_lobby(
    scene_name: str, catalog: PackCatalog
) -> None:
    scene = catalog.scene_registry.get(scene_name)

    assert scene.settings.get("return_to_lobby", "hold_seconds") == 5.0


# --- ir_range_receiver scene discovery (issue #918) ---


def test_ir_range_receiver_scene_local_rule_is_discovered(catalog: PackCatalog) -> None:
    scene_registry = catalog.scene_registry

    scene = scene_registry.get("ir_range_receiver")
    local_rules = scene.local_rule_registry

    rule = local_rules.get("receiver_rule", GameRule)
    assert isinstance(rule, GameRule)


def test_ir_range_receiver_scene_declares_the_basic_effect_pack(catalog: PackCatalog) -> None:
    scene_registry = catalog.scene_registry

    scene = scene_registry.get("ir_range_receiver")

    pack_names = [pack.name for pack in scene.effect_packs]
    assert "basic" in pack_names


def test_ir_range_receiver_scene_declares_no_return_to_lobby_rule_pack(
    catalog: PackCatalog,
) -> None:
    """Minimal bench scene -- no phases, no buttons, no return_to_lobby."""
    scene_registry = catalog.scene_registry

    scene = scene_registry.get("ir_range_receiver")

    rule_pack_names = [pack.name for pack in scene.rule_packs]
    assert rule_pack_names == []


def test_hardware_test_scene_local_effect_sfx_test_is_discovered(catalog: PackCatalog) -> None:
    scene_registry = catalog.scene_registry

    scene = scene_registry.get("hardware_test")
    local_effects = scene.local_effect_registry

    builder = local_effects.get("sfx_test", EffectBuilder)
    assert isinstance(builder, EffectBuilder)


def test_hardware_test_scene_local_sfx_test_produces_no_pixels(catalog: PackCatalog) -> None:
    scene_registry = catalog.scene_registry

    scene = scene_registry.get("hardware_test")
    local_effects = scene.local_effect_registry

    builder = local_effects.get("sfx_test", EffectBuilder)
    config = EffectConfig(resolution=16, options={})
    effect = builder("sfx_test", config)
    assert effect.pixels is None


def test_hardware_test_scene_local_rules_are_discovered(catalog: PackCatalog) -> None:
    scene_registry = catalog.scene_registry

    scene = scene_registry.get("hardware_test")
    local_rules = scene.local_rule_registry

    for rule_name in ("rgb_rule", "motion_rule", "ir_rule", "radio_rule", "sfx_rule"):
        rule = local_rules.get(rule_name, GameRule)
        assert isinstance(rule, GameRule), f"{rule_name} expected to be a GameRule"


def test_hardware_test_scene_json_does_not_list_own_effect_pack(catalog: PackCatalog) -> None:
    scene_registry = catalog.scene_registry

    scene = scene_registry.get("hardware_test")

    pack_names = [pack.name for pack in scene.effect_packs]
    assert "hardware_test" not in pack_names


def test_hardware_test_scene_json_does_not_list_own_rule_pack(catalog: PackCatalog) -> None:
    scene_registry = catalog.scene_registry

    scene = scene_registry.get("hardware_test")

    rule_pack_names = [pack.name for pack in scene.rule_packs]
    assert "hardware_test" not in rule_pack_names


def test_hardware_test_scene_json_does_not_list_debug_rule_pack(catalog: PackCatalog) -> None:
    scene_registry = catalog.scene_registry

    scene = scene_registry.get("hardware_test")

    rule_pack_names = [pack.name for pack in scene.rule_packs]
    assert "debug" not in rule_pack_names


def _namespace_with_active(catalog: PackCatalog, scene_name: str) -> ActiveSceneNamespace:
    """The Active scene namespace with *scene_name* installed, as the game installs it."""
    scene = catalog.scene_registry.get(scene_name)
    namespace = ActiveSceneNamespace(catalog.effect_registry, catalog.pack_sounds)
    namespace.install(
        scene.local_effect_registry,
        scene.local_sound_map,
        frozenset(pack.name for pack in scene.effect_packs),
    )
    return namespace


def _resolve_every_local_clip(catalog: PackCatalog, scene_name: str) -> list[str]:
    """Resolve every clip *scene_name*'s local effects declare, as the game would with it active."""
    local_effects = catalog.scene_registry.get(scene_name).local_effect_registry
    namespace = _namespace_with_active(catalog, scene_name)

    resolved_paths = []
    for effect_name in local_effects.items():
        builder = local_effects.get(effect_name, EffectBuilder)
        effect = builder(effect_name, EffectConfig(resolution=16, options={}))
        if effect.audio is None:
            continue
        for clip in effect.audio.clips.values():
            resolved_paths.append(namespace.resolve_clip(clip.name))
    return resolved_paths


# --- Clip resolution through the Active scene namespace (issue #804) ---


def test_effect_pack_sounds_resolve_qualified_by_their_pack_name(catalog: PackCatalog) -> None:
    namespace = _namespace_with_active(catalog, "hardware_test")

    assert namespace.resolve_clip("basic.game_over_sting_start") == _under_packs(
        "effects/basic/sounds/game_over_sting_start.wav"
    )
    assert namespace.resolve_clip("elements.lightning_strike") == _under_packs(
        "effects/elements/sounds/lightning_strike.wav"
    )


def test_hardware_test_scenes_own_sound_resolves_to_its_sounds_folder(
    catalog: PackCatalog,
) -> None:
    """scene.sfx_test_start is the clip hardware_test's sfx_test effect plays."""
    namespace = _namespace_with_active(catalog, "hardware_test")

    assert namespace.resolve_clip("scene.sfx_test_start") == _under_packs(
        "scenes/hardware_test/sounds/sfx_test_start.wav"
    )


def test_a_device_with_no_audio_still_starts_an_effect_that_declares_a_clip(
    catalog: PackCatalog,
) -> None:
    """Clips resolve the same with or without an audio output, so no-audio devices need no case."""
    effect_manager = EffectManager(
        namespace=_namespace_with_active(catalog, "hardware_test"), outputs=[]
    )

    receipt = effect_manager.set_effect(Scope.PERSONAL, "scene.sfx_test", {})

    assert receipt is not None


# --- Tag scene audio discovery (issue #805) ---


def test_tag_scenes_own_sounds_resolve_to_its_sounds_folder(catalog: PackCatalog) -> None:
    namespace = _namespace_with_active(catalog, "tag")

    for stem in (
        "fire_shot_start",
        "reload",
        "reload_complete",
        "dry_fire_start",
        "ready_shots_start",
        "go_start",
        "warning_pulse_peak",
        "hit_start",
    ):
        assert namespace.resolve_clip(f"scene.{stem}") == _under_packs(
            f"scenes/tag/sounds/{stem}.wav"
        )


def test_tags_game_over_sting_resolves_through_the_basic_pack(catalog: PackCatalog) -> None:
    namespace = _namespace_with_active(catalog, "tag")

    assert namespace.resolve_clip("basic.game_over_sting_start") == _under_packs(
        "effects/basic/sounds/game_over_sting_start.wav"
    )


def test_tag_scene_every_audio_playing_effects_clip_name_resolves(catalog: PackCatalog) -> None:
    """Every tag effect that plays audio names a clip the active scene resolves --
    the shared basic sting via the declared basic pack, everything else via tag's
    own sounds/ -- so the scene can run end-to-end with no unresolved clip."""
    resolved_clip_names = _resolve_every_local_clip(catalog, "tag")

    # Sanity check that the walk actually reached tag's audio-playing effects,
    # so a future scan/discovery regression collapsing this to zero effects
    # doesn't pass silently.
    assert len(resolved_clip_names) == 9


# --- Red Light Green Light scene audio discovery (issue #806) ---


def test_red_light_green_light_scenes_own_sounds_resolve_to_its_sounds_folder(
    catalog: PackCatalog,
) -> None:
    namespace = _namespace_with_active(catalog, "red_light_green_light")

    for stem in (
        "green_light_music_start",
        "red_light_music_start",
        "level_up_start",
        "win_sting_start",
        "ready_start",
        "warning_sting_peak",
    ):
        assert namespace.resolve_clip(f"scene.{stem}") == _under_packs(
            f"scenes/red_light_green_light/sounds/{stem}.wav"
        )


def test_red_light_green_light_game_over_sting_resolves_through_the_basic_pack(
    catalog: PackCatalog,
) -> None:
    namespace = _namespace_with_active(catalog, "red_light_green_light")

    assert namespace.resolve_clip("basic.game_over_sting_start") == _under_packs(
        "effects/basic/sounds/game_over_sting_start.wav"
    )


def test_red_light_green_light_scene_every_audio_playing_effects_clip_name_resolves(
    catalog: PackCatalog,
) -> None:
    """Every rlgl effect that plays audio names a clip the active scene resolves --
    the shared basic sting via the declared basic pack, everything else via rlgl's
    own sounds/ -- so the scene can run end-to-end with no unresolved clip."""
    resolved_clip_names = _resolve_every_local_clip(catalog, "red_light_green_light")

    # Sanity check that the walk actually reached rlgl's audio-playing effects,
    # so a future scan/discovery regression collapsing this to zero effects
    # doesn't pass silently.
    assert len(resolved_clip_names) == 7


# --- SceneManager integration ---


@pytest.fixture
def loaded_debug_engine(catalog: PackCatalog):
    rule_registry = catalog.rule_registry
    effect_registry = catalog.effect_registry
    namespace = ActiveSceneNamespace(effect_registry, catalog.pack_sounds)
    effect_manager = EffectManager(namespace=namespace, outputs=[])
    engine = GameEngine(effect_manager)
    scene_registry = SceneRegistry()
    scene_registry.register(
        "test_scene",
        lambda: Scene(effect_packs=[], rule_packs=[PackReference("debug", Version(1, 0))]),
    )
    manager = SceneManager(
        engine,
        effect_registry,
        rule_registry,
        scene_registry,
        effect_admin=effect_manager,
        namespace=namespace,
        scene_reboot=SceneReboot(),
    )
    manager.activate_boot_scene("test_scene")
    return engine, rule_registry


def test_boot_scene_wires_event_logger_rule_from_pack(
    loaded_debug_engine,
) -> None:
    engine, _ = loaded_debug_engine

    assert any(isinstance(r, EventLoggerRule) for r in engine.rules)


def test_boot_scene_activates_all_rules_from_pack(
    loaded_debug_engine,
) -> None:
    engine, rule_registry = loaded_debug_engine

    expected_count = len(rule_registry.items("debug"))

    assert all(isinstance(r, GameRule) for r in engine.rules)
    assert len(engine.rules) == expected_count
