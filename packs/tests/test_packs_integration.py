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


def test_solid_level_1_white_renders_dimmed_pixels() -> None:
    from effects.render import PixelBuffer, RendererConfig
    from engine.effects.manager import EffectBuilder

    registry = PackRegistry(item_attr="BUILD")
    registry.scan_dir(_packs_path("effects"), "packs.effects")
    builder = registry.get("basic", "solid", EffectBuilder)
    config = RendererConfig(level=1, resolution=16, options={"color": 0xFFFFFF})
    renderer = builder("basic.solid", config)
    output = PixelBuffer(4)

    renderer.render(None, output)  # type: ignore[arg-type]

    assert all(output[i] == 0x191919 for i in range(4))


def test_solid_level_10_white_renders_full_brightness() -> None:
    from effects.render import PixelBuffer, RendererConfig
    from engine.effects.manager import EffectBuilder

    registry = PackRegistry(item_attr="BUILD")
    registry.scan_dir(_packs_path("effects"), "packs.effects")
    builder = registry.get("basic", "solid", EffectBuilder)
    config = RendererConfig(level=10, resolution=16, options={"color": 0xFFFFFF})
    renderer = builder("basic.solid", config)
    output = PixelBuffer(4)

    renderer.render(None, output)  # type: ignore[arg-type]

    assert all(output[i] == 0xFFFFFF for i in range(4))


def test_solid_level_5_red_renders_half_brightness() -> None:
    from effects.render import PixelBuffer, RendererConfig
    from engine.effects.manager import EffectBuilder

    registry = PackRegistry(item_attr="BUILD")
    registry.scan_dir(_packs_path("effects"), "packs.effects")
    builder = registry.get("basic", "solid", EffectBuilder)
    config = RendererConfig(level=5, resolution=16, options={"color": 0xFF0000})
    renderer = builder("basic.solid", config)
    output = PixelBuffer(4)

    renderer.render(None, output)  # type: ignore[arg-type]

    assert all(output[i] == 0x7F0000 for i in range(4))


def test_solid_defaults_to_white_when_no_options() -> None:
    from effects.render import PixelBuffer, RendererConfig
    from engine.effects.manager import EffectBuilder

    registry = PackRegistry(item_attr="BUILD")
    registry.scan_dir(_packs_path("effects"), "packs.effects")
    builder = registry.get("basic", "solid", EffectBuilder)
    config = RendererConfig(level=10, resolution=16)
    renderer = builder("basic.solid", config)
    output = PixelBuffer(4)

    renderer.render(None, output)  # type: ignore[arg-type]

    assert all(output[i] == 0xFFFFFF for i in range(4))


def test_solid_double_render_is_pixel_identical() -> None:
    from effects.render import PixelBuffer, RendererConfig
    from engine.effects.manager import EffectBuilder

    registry = PackRegistry(item_attr="BUILD")
    registry.scan_dir(_packs_path("effects"), "packs.effects")
    builder = registry.get("basic", "solid", EffectBuilder)
    config = RendererConfig(level=7, resolution=16, options={"color": 0x00FF80})
    renderer = builder("basic.solid", config)
    output1 = PixelBuffer(8)
    output2 = PixelBuffer(8)

    renderer.render(None, output1)  # type: ignore[arg-type]
    renderer.render(None, output2)  # type: ignore[arg-type]

    assert all(output1[i] == output2[i] for i in range(8))


def test_solid_renderer_name_is_basic_solid() -> None:
    from effects.render import RendererConfig
    from engine.effects.manager import EffectBuilder

    registry = PackRegistry(item_attr="BUILD")
    registry.scan_dir(_packs_path("effects"), "packs.effects")
    builder = registry.get("basic", "solid", EffectBuilder)
    config = RendererConfig(level=5, resolution=16)
    renderer = builder("basic.solid", config)

    assert renderer.name == "basic.solid"


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
    rule_registry = PackRegistry(item_attr="RULE")
    rule_registry.scan_dir(_packs_path("rules"), "packs.rules")
    effect_registry = PackRegistry(item_attr="BUILD")
    engine = GameEngine(EffectControls())
    manager = SceneManager(engine, effect_registry, rule_registry)
    manager.register(
        "test_scene",
        lambda: Scene(rules=[], effect_packs=[], rule_packs=[("debug", "99.0")]),
    )

    with pytest.raises(ValueError):
        manager.load("test_scene")
