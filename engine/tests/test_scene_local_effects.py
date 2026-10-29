"""Tests for scene-local effect discovery, the scene. prefix resolution,
and overlay isolation semantics.
"""

from __future__ import annotations

from unittest.mock import ANY

import pytest

from engine.effects.manager import EffectManager
from engine.events import EffectEvent
from engine.namespace import ActiveSceneNamespace
from engine.packs import PackRegistry, UnknownItemError
from engine.scene import Scene
from engine.state import Scope
from engine.tests.effects.helpers import SpyEffectOutput
from engine.tests.helpers import (
    RecordingNamespace,
    make_scene_manager,
)
from engine.timer import Timer

# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------


def _stub_effect_source() -> str:
    return (
        "from engine.tests.effects.helpers import StubEffectBuilder\nBUILD = StubEffectBuilder()\n"
    )


def _local_effects(*names: str) -> dict[str, dict]:
    """Return ``pack_tree.scene`` fields giving a scene a stub local effect per name."""
    return {"effects": {name: _stub_effect_source() for name in names}}


def _make_effect_manager(scene: Scene, outputs=None) -> EffectManager:
    """Return an EffectManager whose namespace has *scene*'s view installed."""
    namespace = ActiveSceneNamespace(PackRegistry(), {})
    namespace.install(scene.local_effect_registry, scene.local_sound_map, frozenset())
    return EffectManager(namespace=namespace, outputs=outputs or [])


# ---------------------------------------------------------------------------
# SceneLocalRegistry — effects/ folder discovery via scan_pack_roots
# ---------------------------------------------------------------------------


def test_a_scenes_effects_folder_items_are_its_local_effects(pack_tree) -> None:
    registry = pack_tree.scan(scenes={"forest": _local_effects("victory_flash")}).scene_registry

    scene = registry.get("forest")
    assert "victory_flash" in scene.local_effect_registry.items()


def test_a_scene_without_an_effects_folder_has_an_empty_local_effect_registry(
    pack_tree,
) -> None:
    registry = pack_tree.scan(scenes={"bare_scene": {}}).scene_registry

    scene = registry.get("bare_scene")
    assert scene.local_effect_registry.items() == []


def test_each_fresh_scene_shares_one_local_effect_registry(pack_tree) -> None:
    registry = pack_tree.scan(scenes={"forest": _local_effects("flash")}).scene_registry

    scene_a = registry.get("forest")
    scene_b = registry.get("forest")
    assert scene_a.local_effect_registry is scene_b.local_effect_registry


def test_a_scenes_local_effects_are_not_visible_to_another_scene(pack_tree) -> None:
    registry = pack_tree.scan(
        scenes={"forest": _local_effects("secret_flash"), "cave": {}}
    ).scene_registry

    cave_scene = registry.get("cave")
    assert "secret_flash" not in cave_scene.local_effect_registry.items()


def test_scene_constructed_directly_has_empty_local_effect_registry() -> None:
    scene = Scene(effect_packs=[], rule_packs=[])
    assert scene.local_effect_registry.items() == []


# ---------------------------------------------------------------------------
# EffectManager — scene. names resolve through the installed scene view
# ---------------------------------------------------------------------------


def test_scene_prefix_resolves_local_effect_when_scene_is_active(pack_tree) -> None:
    registry = pack_tree.scan(scenes={"forest": _local_effects("flash")}).scene_registry
    output = SpyEffectOutput(min_resolution=16, scopes=[Scope.PERSONAL])
    manager = _make_effect_manager(registry.get("forest"), outputs=[output])

    manager.set_effect(Scope.PERSONAL, "scene.flash", {})
    manager.update(Timer())

    assert output.update_pixels_calls == [("personal", output.created_buffers[0])]


def test_scene_prefix_fires_start_event_with_pack_equals_scene(pack_tree) -> None:
    registry = pack_tree.scan(scenes={"forest": _local_effects("flash")}).scene_registry
    output = SpyEffectOutput(min_resolution=16, scopes=[Scope.PERSONAL])
    manager = _make_effect_manager(registry.get("forest"), outputs=[output])

    receipt = manager.set_effect(Scope.PERSONAL, "scene.flash", {})

    assert output.handle_event_calls == [
        (EffectEvent("scene", "flash", "start"), frozenset({"personal"}), ANY, receipt)
    ]


# ---------------------------------------------------------------------------
# SceneManager installs the active scene's local effects on transitions
# ---------------------------------------------------------------------------


def test_scene_manager_installs_local_effects_on_load(pack_tree) -> None:
    catalog = pack_tree.scan(scenes={"forest": _local_effects("flash")})
    namespace = RecordingNamespace()
    manager = make_scene_manager(catalog, namespace=namespace)

    manager.load("forest")
    manager.update()

    [(local_effects, _, _)] = namespace.installs
    assert local_effects.items() == ["flash"]


def test_scene_manager_installs_overlay_scene_local_effects_on_overlay(pack_tree) -> None:
    catalog = pack_tree.scan(scenes={"scene_b": _local_effects("b_flash"), "scene_a": {}})
    namespace = RecordingNamespace()
    manager = make_scene_manager(catalog, namespace=namespace)
    manager.load("scene_a")
    manager.update()

    manager.overlay("scene_b")
    manager.update()

    local_effects, _, _ = namespace.installs[-1]
    assert local_effects.items() == ["b_flash"]


def test_scene_manager_restores_base_local_effects_on_pop(pack_tree) -> None:
    catalog = pack_tree.scan(
        scenes={"scene_a": _local_effects("a_flash"), "scene_b": _local_effects("b_flash")}
    )
    namespace = RecordingNamespace()
    manager = make_scene_manager(catalog, namespace=namespace)
    manager.load("scene_a")
    manager.update()
    manager.overlay("scene_b")
    manager.update()

    manager.pop()
    manager.update()

    local_effects, _, _ = namespace.installs[-1]
    assert local_effects.items() == ["a_flash"]


# ---------------------------------------------------------------------------
# SceneManager installs the active scene's local sounds on transitions
# ---------------------------------------------------------------------------


def test_scene_manager_installs_scene_sounds_on_load(pack_tree) -> None:
    catalog = pack_tree.scan(scenes={"forest": {"sounds": ["victory_sting"]}})
    namespace = RecordingNamespace()
    manager = make_scene_manager(catalog, namespace=namespace)

    manager.load("forest")
    manager.update()

    [(_, local_sounds, _)] = namespace.installs
    assert list(local_sounds) == ["victory_sting"]


def test_scene_manager_installs_no_sounds_for_a_scene_with_none(pack_tree) -> None:
    catalog = pack_tree.scan(scenes={"bare_scene": {}})
    namespace = RecordingNamespace()
    manager = make_scene_manager(catalog, namespace=namespace)

    manager.load("bare_scene")
    manager.update()

    [(_, local_sounds, _)] = namespace.installs
    assert local_sounds == {}


def test_scene_manager_installs_overlay_scene_sounds_on_overlay(pack_tree) -> None:
    catalog = pack_tree.scan(scenes={"scene_b": {"sounds": ["b_sting"]}, "scene_a": {}})
    namespace = RecordingNamespace()
    manager = make_scene_manager(catalog, namespace=namespace)
    manager.load("scene_a")
    manager.update()

    manager.overlay("scene_b")
    manager.update()

    _, local_sounds, _ = namespace.installs[-1]
    assert list(local_sounds) == ["b_sting"]


def test_scene_manager_restores_base_scene_sounds_on_pop(pack_tree) -> None:
    catalog = pack_tree.scan(
        scenes={
            "scene_a": {"sounds": ["a_sting"]},
            "scene_b": {"sounds": ["b_sting"]},
        },
    )
    namespace = RecordingNamespace()
    manager = make_scene_manager(catalog, namespace=namespace)
    manager.load("scene_a")
    manager.update()
    manager.overlay("scene_b")
    manager.update()

    manager.pop()
    manager.update()

    _, local_sounds, _ = namespace.installs[-1]
    assert list(local_sounds) == ["a_sting"]


# ---------------------------------------------------------------------------
# Isolation: scene-local effect not reachable from another scene
# ---------------------------------------------------------------------------


def test_loading_scene_b_after_a_does_not_expose_scene_a_locals(pack_tree) -> None:
    scene_registry = pack_tree.scan(
        scenes={"scene_a": _local_effects("secret"), "scene_b": {}}
    ).scene_registry
    manager = _make_effect_manager(scene_registry.get("scene_b"))

    with pytest.raises(UnknownItemError):
        manager.set_effect(Scope.PERSONAL, "scene.secret", {})
