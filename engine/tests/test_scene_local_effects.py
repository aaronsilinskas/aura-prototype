"""Tests for scene-local effect discovery, the scene. prefix resolution,
and overlay isolation semantics.
"""

from __future__ import annotations

from unittest.mock import ANY

import pytest

from engine.effects.manager import EffectManager
from engine.engine import GameEngine
from engine.events import EffectEvent
from engine.pack_catalog import PackCatalog, scan_pack_roots
from engine.packs import PackRegistry
from engine.scene import Scene, SceneLocalRegistry, SceneManager
from engine.state import EffectAdmin, EffectControls, Scope
from engine.tests.effects.helpers import SpyEffectOutput
from engine.tests.helpers import RecordingSceneReboot, SpyAudioOverlayAdmin, SpyEffectAdmin
from engine.timer import Timer

# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

ROOT_NAME = "tse_flash"


def _stub_effect_source() -> str:
    return (
        "from engine.tests.effects.helpers import StubEffectBuilder\nBUILD = StubEffectBuilder()\n"
    )


def _scan(pack_tree, scenes: dict[str, dict]) -> PackCatalog:
    """Scan one root holding *scenes*, each name mapped to its ``pack_tree.scene`` fields."""
    root = pack_tree.root(ROOT_NAME)
    for name, fields in scenes.items():
        pack_tree.scene(root, name, **fields)
    return scan_pack_roots([str(root)])


def _local_effects(*names: str) -> dict[str, dict]:
    """Return ``pack_tree.scene`` fields giving a scene a stub local effect per name."""
    return {"effects": {name: _stub_effect_source() for name in names}}


class _RecordingEffectControls(EffectControls):
    """Records stop_effect calls.

    Local-effects pushes no longer go through ``EffectControls`` — see
    ``SpyEffectAdmin`` for those.
    """

    def __init__(self) -> None:
        self.stopped_scopes: list = []

    def stop_effect(self, scope) -> None:
        self.stopped_scopes.append(scope)


def _make_scene_manager(
    catalog: PackCatalog,
    effect_admin: SpyEffectAdmin | None = None,
    audio_overlay_admin: SpyAudioOverlayAdmin | None = None,
) -> SceneManager:
    """Construct a SceneManager over *catalog*'s registries with spy admins."""
    return SceneManager(
        GameEngine(effect_controls=_RecordingEffectControls()),
        catalog.effect_registry,
        catalog.rule_registry,
        catalog.scene_registry,
        effect_admin or SpyEffectAdmin(),
        audio_overlay_admin or SpyAudioOverlayAdmin(),
        RecordingSceneReboot(),
    )


def _make_effect_manager(outputs=None) -> EffectManager:
    return EffectManager(registry=PackRegistry(), outputs=outputs or [])


# ---------------------------------------------------------------------------
# SceneLocalRegistry — effects/ folder discovery via scan_pack_roots
# ---------------------------------------------------------------------------


def test_a_scenes_effects_folder_items_are_its_local_effects(pack_tree) -> None:
    registry = _scan(pack_tree, {"forest": _local_effects("victory_flash")}).scene_registry

    scene = registry.get("forest")
    assert "victory_flash" in scene.local_effect_registry.items()


def test_a_scene_without_an_effects_folder_has_an_empty_local_effect_registry(
    pack_tree,
) -> None:
    registry = _scan(pack_tree, {"bare_scene": {}}).scene_registry

    scene = registry.get("bare_scene")
    assert scene.local_effect_registry.items() == []


def test_init_py_is_not_a_local_effect(pack_tree) -> None:
    root = pack_tree.root(ROOT_NAME)
    scene_dir = pack_tree.scene(root, "forest", **_local_effects("flash"))
    (scene_dir / "effects" / "__init__.py").write_text("")

    registry = scan_pack_roots([str(root)]).scene_registry

    scene = registry.get("forest")
    assert "__init__" not in scene.local_effect_registry.items()
    assert "flash" in scene.local_effect_registry.items()


def test_a_subfolder_of_the_effects_folder_is_not_a_local_effect(pack_tree) -> None:
    root = pack_tree.root(ROOT_NAME)
    scene_dir = pack_tree.scene(root, "forest", **_local_effects("flash"))
    tests_dir = scene_dir / "effects" / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_flash.py").write_text("")

    registry = scan_pack_roots([str(root)]).scene_registry

    scene = registry.get("forest")
    assert "tests" not in scene.local_effect_registry.items()
    assert "flash" in scene.local_effect_registry.items()


def test_each_fresh_scene_shares_one_local_effect_registry(pack_tree) -> None:
    registry = _scan(pack_tree, {"forest": _local_effects("flash")}).scene_registry

    scene_a = registry.get("forest")
    scene_b = registry.get("forest")
    assert scene_a.local_effect_registry is scene_b.local_effect_registry


def test_a_scenes_local_effects_are_not_visible_to_another_scene(pack_tree) -> None:
    registry = _scan(
        pack_tree, {"forest": _local_effects("secret_flash"), "cave": {}}
    ).scene_registry

    cave_scene = registry.get("cave")
    assert "secret_flash" not in cave_scene.local_effect_registry.items()


def test_scene_constructed_directly_has_empty_local_effect_registry() -> None:
    scene = Scene(effect_packs=[], rule_packs=[])
    assert scene.local_effect_registry.items() == []


# ---------------------------------------------------------------------------
# EffectAdmin — base class raises, documented reserved for SceneManager
# ---------------------------------------------------------------------------


def test_effect_admin_base_class_set_local_effects_raises_not_implemented_error() -> None:
    admin = EffectAdmin()

    with pytest.raises(NotImplementedError):
        admin.set_local_effects(SceneLocalRegistry())


# ---------------------------------------------------------------------------
# EffectManager.set_local_effects — installs and replaces the active registry
# ---------------------------------------------------------------------------


def test_effect_manager_set_local_effects_enables_scene_prefix_resolution(
    pack_tree,
) -> None:
    registry = _scan(pack_tree, {"forest": _local_effects("flash")}).scene_registry
    scene = registry.get("forest")

    manager = _make_effect_manager()
    manager.set_local_effects(scene.local_effect_registry)

    # If the registry was stored, scene.flash must resolve without error
    receipt = manager.set_effect(Scope.PERSONAL, "scene.flash", {})
    assert receipt is not None


def test_effect_manager_set_local_effects_none_causes_scene_prefix_to_fail(
    pack_tree,
) -> None:
    registry = _scan(pack_tree, {"forest": _local_effects("flash")}).scene_registry
    scene = registry.get("forest")

    manager = _make_effect_manager()
    manager.set_local_effects(scene.local_effect_registry)
    manager.set_local_effects(None)  # clear

    with pytest.raises(ValueError, match="no scene is active"):
        manager.set_effect(Scope.PERSONAL, "scene.flash", {})


# ---------------------------------------------------------------------------
# EffectManager._build_effect — scene. prefix routing
# ---------------------------------------------------------------------------


def test_scene_prefix_with_no_active_scene_raises_at_set_effect() -> None:
    manager = _make_effect_manager()
    # No scene loaded — _local_effects is None

    with pytest.raises(ValueError, match="no scene is active"):
        manager.set_effect(Scope.PERSONAL, "scene.flash", {})


def test_scene_prefix_resolves_local_effect_when_scene_is_active(pack_tree) -> None:
    registry = _scan(pack_tree, {"forest": _local_effects("flash")}).scene_registry

    scene = registry.get("forest")
    output = SpyEffectOutput(min_resolution=16, scopes=[Scope.PERSONAL])
    manager = EffectManager(registry=PackRegistry(), outputs=[output])
    manager.set_local_effects(scene.local_effect_registry)

    manager.set_effect(Scope.PERSONAL, "scene.flash", {})
    manager.update(Timer())

    assert output.update_pixels_calls == [("personal", output.created_buffers[0])]


def test_scene_prefix_unknown_effect_raises_with_effect_name_in_message(pack_tree) -> None:
    registry = _scan(pack_tree, {"forest": _local_effects("flash")}).scene_registry

    scene = registry.get("forest")
    manager = _make_effect_manager()
    manager.set_local_effects(scene.local_effect_registry)

    with pytest.raises(ValueError, match="missing_effect"):
        manager.set_effect(Scope.PERSONAL, "scene.missing_effect", {})


def test_scene_prefix_fires_start_event_with_pack_equals_scene(pack_tree) -> None:
    registry = _scan(pack_tree, {"forest": _local_effects("flash")}).scene_registry

    scene = registry.get("forest")
    output = SpyEffectOutput(min_resolution=16, scopes=[Scope.PERSONAL])
    manager = EffectManager(registry=PackRegistry(), outputs=[output])
    manager.set_local_effects(scene.local_effect_registry)

    receipt = manager.set_effect(Scope.PERSONAL, "scene.flash", {})

    assert output.handle_event_calls == [
        (EffectEvent("scene", "flash", "start"), frozenset({"personal"}), ANY, receipt)
    ]


# ---------------------------------------------------------------------------
# SceneManager pushes local effect registry on transitions
# ---------------------------------------------------------------------------


def test_scene_manager_pushes_local_effects_on_load(pack_tree) -> None:
    catalog = _scan(pack_tree, {"forest": _local_effects("flash")})

    effect_admin = SpyEffectAdmin()
    manager = _make_scene_manager(catalog, effect_admin=effect_admin)
    manager.load("forest")
    manager.update()

    assert len(effect_admin.local_effects_history) == 1
    pushed = effect_admin.local_effects_history[0]
    assert isinstance(pushed, SceneLocalRegistry)
    assert "flash" in pushed.items()


def test_scene_manager_load_replaces_active_scene_registry_with_new_scenes(pack_tree) -> None:
    """When load replaces the current scene, the new scene's registry is pushed once."""
    catalog = _scan(pack_tree, {"a": {}, "b": {}})

    effect_admin = SpyEffectAdmin()
    manager = _make_scene_manager(catalog, effect_admin=effect_admin)

    manager.load("a")
    manager.update()
    effect_admin.local_effects_history.clear()

    manager.load("b")
    manager.update()

    # One push: the new scene b's (empty) local effect registry
    assert len(effect_admin.local_effects_history) == 1


def test_scene_manager_pushes_overlay_scene_local_effects_on_overlay(pack_tree) -> None:
    catalog = _scan(pack_tree, {"scene_b": _local_effects("b_flash"), "scene_a": {}})

    effect_admin = SpyEffectAdmin()
    manager = _make_scene_manager(catalog, effect_admin=effect_admin)

    manager.load("scene_a")
    manager.update()
    effect_admin.local_effects_history.clear()

    manager.overlay("scene_b")
    manager.update()

    assert len(effect_admin.local_effects_history) == 1
    pushed = effect_admin.local_effects_history[0]
    assert "b_flash" in pushed.items()


def test_scene_manager_restores_base_local_effects_on_pop(pack_tree) -> None:
    catalog = _scan(
        pack_tree, {"scene_a": _local_effects("a_flash"), "scene_b": _local_effects("b_flash")}
    )

    effect_admin = SpyEffectAdmin()
    manager = _make_scene_manager(catalog, effect_admin=effect_admin)

    manager.load("scene_a")
    manager.update()
    manager.overlay("scene_b")
    manager.update()
    effect_admin.local_effects_history.clear()

    manager.pop()
    manager.update()

    assert len(effect_admin.local_effects_history) == 1
    pushed = effect_admin.local_effects_history[0]
    assert "a_flash" in pushed.items()
    assert "b_flash" not in pushed.items()


# ---------------------------------------------------------------------------
# SceneManager installs the active scene's sound overlay on transitions
# ---------------------------------------------------------------------------


def test_scene_manager_installs_scene_sound_overlay_on_load(pack_tree) -> None:
    catalog = _scan(pack_tree, {"forest": {"sounds": ["victory_sting"]}})

    audio_overlay_admin = SpyAudioOverlayAdmin()
    manager = _make_scene_manager(catalog, audio_overlay_admin=audio_overlay_admin)
    manager.load("forest")
    manager.update()

    assert len(audio_overlay_admin.scene_sounds_history) == 1
    pushed = audio_overlay_admin.scene_sounds_history[0]
    assert "victory_sting" in pushed


def test_scene_manager_load_installs_none_overlay_for_scene_with_no_sounds(pack_tree) -> None:
    catalog = _scan(pack_tree, {"bare_scene": {}})

    audio_overlay_admin = SpyAudioOverlayAdmin()
    manager = _make_scene_manager(catalog, audio_overlay_admin=audio_overlay_admin)
    manager.load("bare_scene")
    manager.update()

    assert audio_overlay_admin.scene_sounds_history == [None]


def test_scene_manager_installs_overlay_scene_sounds_on_overlay(pack_tree) -> None:
    catalog = _scan(pack_tree, {"scene_b": {"sounds": ["b_sting"]}, "scene_a": {}})

    audio_overlay_admin = SpyAudioOverlayAdmin()
    manager = _make_scene_manager(catalog, audio_overlay_admin=audio_overlay_admin)

    manager.load("scene_a")
    manager.update()
    audio_overlay_admin.scene_sounds_history.clear()

    manager.overlay("scene_b")
    manager.update()

    assert len(audio_overlay_admin.scene_sounds_history) == 1
    pushed = audio_overlay_admin.scene_sounds_history[0]
    assert "b_sting" in pushed


def test_scene_manager_restores_base_scene_sounds_on_pop(pack_tree) -> None:
    catalog = _scan(
        pack_tree,
        {
            "scene_a": {"sounds": ["a_sting"]},
            "scene_b": {"sounds": ["b_sting"]},
        },
    )

    audio_overlay_admin = SpyAudioOverlayAdmin()
    manager = _make_scene_manager(catalog, audio_overlay_admin=audio_overlay_admin)

    manager.load("scene_a")
    manager.update()
    manager.overlay("scene_b")
    manager.update()
    audio_overlay_admin.scene_sounds_history.clear()

    manager.pop()
    manager.update()

    assert len(audio_overlay_admin.scene_sounds_history) == 1
    pushed = audio_overlay_admin.scene_sounds_history[0]
    assert "a_sting" in pushed
    assert "b_sting" not in pushed


# ---------------------------------------------------------------------------
# Isolation: scene-local effect not reachable from another scene
# ---------------------------------------------------------------------------


def test_loading_scene_b_after_a_does_not_expose_scene_a_locals(pack_tree) -> None:
    scene_registry = _scan(
        pack_tree, {"scene_a": _local_effects("secret"), "scene_b": {}}
    ).scene_registry

    output = SpyEffectOutput(min_resolution=16, scopes=[Scope.PERSONAL])
    manager = EffectManager(registry=PackRegistry(), outputs=[output])

    scene_b = scene_registry.get("scene_b")
    manager.set_local_effects(scene_b.local_effect_registry)

    with pytest.raises(ValueError):
        manager.set_effect(Scope.PERSONAL, "scene.secret", {})


# ---------------------------------------------------------------------------
# Overlay replace semantics: B's locals only; A's unreachable while B on top
# ---------------------------------------------------------------------------


def test_overlay_b_on_a_resolves_scene_prefix_against_b_locals_only(pack_tree) -> None:
    """With B overlaid on A, scene.* resolves against B's locals only."""
    scene_registry = _scan(
        pack_tree, {"scene_a": _local_effects("a_only"), "scene_b": _local_effects("b_only")}
    ).scene_registry

    output = SpyEffectOutput(min_resolution=16, scopes=[Scope.PERSONAL])
    manager = EffectManager(registry=PackRegistry(), outputs=[output])

    # Simulate B overlaid on A: push B's locals
    scene_b = scene_registry.get("scene_b")
    manager.set_local_effects(scene_b.local_effect_registry)

    # A's local 'a_only' must not be reachable from B's context
    with pytest.raises(ValueError, match="a_only"):
        manager.set_effect(Scope.PERSONAL, "scene.a_only", {})


def test_overlay_b_on_a_after_pop_a_locals_restored(pack_tree) -> None:
    """After B pops, A's locals are reachable again."""
    scene_registry = _scan(
        pack_tree, {"scene_a": _local_effects("a_only"), "scene_b": _local_effects("b_only")}
    ).scene_registry

    output = SpyEffectOutput(min_resolution=16, scopes=[Scope.PERSONAL])
    manager = EffectManager(registry=PackRegistry(), outputs=[output])

    # Simulate B overlaid then popped — A restored
    scene_a = scene_registry.get("scene_a")
    manager.set_local_effects(scene_a.local_effect_registry)

    # A's local effect must resolve successfully after restore
    receipt = manager.set_effect(Scope.PERSONAL, "scene.a_only", {})
    assert receipt is not None


# ---------------------------------------------------------------------------
# EffectEvent.pack == "scene" for scene-local effects
# ---------------------------------------------------------------------------


def test_effect_event_pack_is_scene_for_scene_local_effect(pack_tree) -> None:
    scene_reg = _scan(pack_tree, {"forest": _local_effects("flash")}).scene_registry
    scene = scene_reg.get("forest")

    output = SpyEffectOutput(min_resolution=16, scopes=[Scope.PERSONAL])
    manager = EffectManager(registry=PackRegistry(), outputs=[output])
    manager.set_local_effects(scene.local_effect_registry)

    manager.set_effect(Scope.PERSONAL, "scene.flash", {})

    start_event = output.handle_event_calls[0][0]
    assert start_event.pack == "scene"
    assert start_event.name == "flash"
