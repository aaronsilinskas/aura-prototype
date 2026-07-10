"""Tests for scene-local effect discovery, the scene. prefix resolution,
the reserved 'scene' pack name guard, and overlay isolation semantics.
"""

from __future__ import annotations

import json
import sys
from unittest.mock import ANY

import pytest

from engine.effects.manager import EffectManager
from engine.engine import GameEngine
from engine.events import EffectEvent
from engine.packs import PackRegistry
from engine.scene import Scene, SceneLocalRegistry, SceneManager, SceneRegistry
from engine.state import EffectAdmin, EffectControls, Scope
from engine.tests.effects.helpers import SpyEffectOutput
from engine.tests.helpers import SpyEffectAdmin
from engine.timer import Timer

# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

MODULE_PREFIX = "tse"
_GROUP_NAME = "tse_group"


@pytest.fixture()
def scene_env(tmp_path):
    """Yield a ``tse/`` directory as the scenes root; manage sys.path / sys.modules."""
    scenes_root = tmp_path / MODULE_PREFIX
    scenes_root.mkdir()
    sys.path.insert(0, str(tmp_path))
    known_modules = set(sys.modules)
    yield scenes_root
    for key in list(sys.modules):
        if key not in known_modules:
            del sys.modules[key]
    sys.path.remove(str(tmp_path))


def _write_scene_json(path, data: dict) -> None:
    (path / "scene.json").write_text(json.dumps(data))


def _minimal_scene_json(**overrides) -> dict:
    base = {"version": "1.0", "effect_packs": [], "rule_packs": []}
    base.update(overrides)
    return base


def _make_scene_dir(root, name: str, **json_overrides):
    scene_dir = root / name
    scene_dir.mkdir(parents=True, exist_ok=True)
    _write_scene_json(scene_dir, _minimal_scene_json(**json_overrides))
    return scene_dir


def _stub_effect_source() -> str:
    return (
        "from engine.tests.effects.helpers import StubEffectBuilder\nBUILD = StubEffectBuilder()\n"
    )


def _make_effects_subdir(scene_dir, items: dict[str, str]) -> None:
    """Create an effects/ subdir under *scene_dir* with .py item files."""
    effects_dir = scene_dir / "effects"
    effects_dir.mkdir(exist_ok=True)
    for name, content in items.items():
        (effects_dir / (name + ".py")).write_text(content)


class _RecordingEffectControls(EffectControls):
    """Records stop_effect calls.

    Local-effects pushes no longer go through ``EffectControls`` — see
    ``SpyEffectAdmin`` for those.
    """

    def __init__(self) -> None:
        self.stopped_scopes: list = []

    def stop_effect(self, scope) -> None:
        self.stopped_scopes.append(scope)


def _make_engine(controls=None) -> GameEngine:
    if controls is None:
        controls = _RecordingEffectControls()
    return GameEngine(effect_controls=controls)


def _make_effect_manager(outputs=None) -> EffectManager:
    return EffectManager(registry=PackRegistry(item_attr="BUILD"), outputs=outputs or [])


# ---------------------------------------------------------------------------
# SceneLocalRegistry — effects/ subdir discovery via SceneRegistry.scan_dir
# ---------------------------------------------------------------------------


def test_scan_dir_exposes_effects_subdir_items_via_local_effect_registry(scene_env) -> None:
    scene_dir = _make_scene_dir(scene_env, "forest")
    _make_effects_subdir(scene_dir, {"victory_flash": _stub_effect_source()})

    registry = SceneRegistry()
    registry.scan_dir(str(scene_env), MODULE_PREFIX)

    scene = registry.get("forest")
    assert "victory_flash" in scene.local_effect_registry.items()


def test_scan_dir_scene_with_no_effects_subdir_has_empty_local_effect_registry(
    scene_env,
) -> None:
    _make_scene_dir(scene_env, "bare_scene")
    registry = SceneRegistry()
    registry.scan_dir(str(scene_env), MODULE_PREFIX)

    scene = registry.get("bare_scene")
    assert scene.local_effect_registry.items() == []


def test_scan_dir_excludes_init_py_from_effect_item_names(scene_env) -> None:
    scene_dir = _make_scene_dir(scene_env, "forest")
    effects_dir = scene_dir / "effects"
    effects_dir.mkdir()
    (effects_dir / "__init__.py").write_text("")
    (effects_dir / "flash.py").write_text(_stub_effect_source())

    registry = SceneRegistry()
    registry.scan_dir(str(scene_env), MODULE_PREFIX)

    scene = registry.get("forest")
    assert "__init__" not in scene.local_effect_registry.items()
    assert "flash" in scene.local_effect_registry.items()


def test_scan_dir_excludes_subdirs_from_effect_item_names(scene_env) -> None:
    scene_dir = _make_scene_dir(scene_env, "forest")
    effects_dir = scene_dir / "effects"
    effects_dir.mkdir()
    (effects_dir / "flash.py").write_text(_stub_effect_source())
    tests_dir = effects_dir / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_flash.py").write_text("")

    registry = SceneRegistry()
    registry.scan_dir(str(scene_env), MODULE_PREFIX)

    scene = registry.get("forest")
    assert "tests" not in scene.local_effect_registry.items()
    assert "flash" in scene.local_effect_registry.items()


def test_scan_dir_local_effect_registry_shared_across_fresh_scene_instances(scene_env) -> None:
    scene_dir = _make_scene_dir(scene_env, "forest")
    _make_effects_subdir(scene_dir, {"flash": _stub_effect_source()})

    registry = SceneRegistry()
    registry.scan_dir(str(scene_env), MODULE_PREFIX)

    scene_a = registry.get("forest")
    scene_b = registry.get("forest")
    assert scene_a.local_effect_registry is scene_b.local_effect_registry


def test_scan_dir_local_effects_not_visible_to_other_scene(scene_env) -> None:
    scene_a_dir = _make_scene_dir(scene_env, "forest")
    _make_effects_subdir(scene_a_dir, {"secret_flash": _stub_effect_source()})
    _make_scene_dir(scene_env, "cave")

    registry = SceneRegistry()
    registry.scan_dir(str(scene_env), MODULE_PREFIX)

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
        admin.set_local_effects(SceneLocalRegistry(item_attr="BUILD"))


# ---------------------------------------------------------------------------
# EffectManager.set_local_effects — installs and replaces the active registry
# ---------------------------------------------------------------------------


def test_effect_manager_set_local_effects_enables_scene_prefix_resolution(
    scene_env,
) -> None:
    scene_dir = _make_scene_dir(scene_env, "forest")
    _make_effects_subdir(scene_dir, {"flash": _stub_effect_source()})

    registry = SceneRegistry()
    registry.scan_dir(str(scene_env), MODULE_PREFIX)
    scene = registry.get("forest")

    manager = _make_effect_manager()
    manager.set_local_effects(scene.local_effect_registry)

    # If the registry was stored, scene.flash must resolve without error
    receipt = manager.set_effect(Scope.PERSONAL, "scene.flash", {})
    assert receipt is not None


def test_effect_manager_set_local_effects_none_causes_scene_prefix_to_fail(
    scene_env,
) -> None:
    scene_dir = _make_scene_dir(scene_env, "forest")
    _make_effects_subdir(scene_dir, {"flash": _stub_effect_source()})

    registry = SceneRegistry()
    registry.scan_dir(str(scene_env), MODULE_PREFIX)
    scene = registry.get("forest")

    manager = _make_effect_manager()
    manager.set_local_effects(scene.local_effect_registry)
    manager.set_local_effects(None)  # clear

    with pytest.raises(ValueError, match="no scene is active"):
        manager.set_effect(Scope.PERSONAL, "scene.flash", {})


# ---------------------------------------------------------------------------
# EffectManager._build_effect — scene. prefix routing
# ---------------------------------------------------------------------------


def test_scene_prefix_with_no_active_scene_raises_at_set_effect(scene_env) -> None:
    manager = _make_effect_manager()
    # No scene loaded — _local_effects is None

    with pytest.raises(ValueError, match="no scene is active"):
        manager.set_effect(Scope.PERSONAL, "scene.flash", {})


def test_scene_prefix_resolves_local_effect_when_scene_is_active(scene_env) -> None:
    scene_dir = _make_scene_dir(scene_env, "forest")
    _make_effects_subdir(scene_dir, {"flash": _stub_effect_source()})

    registry = SceneRegistry()
    registry.scan_dir(str(scene_env), MODULE_PREFIX)

    scene = registry.get("forest")
    output = SpyEffectOutput(min_resolution=16, scopes=[Scope.PERSONAL])
    manager = EffectManager(registry=PackRegistry(item_attr="BUILD"), outputs=[output])
    manager.set_local_effects(scene.local_effect_registry)

    manager.set_effect(Scope.PERSONAL, "scene.flash", {})
    manager.update(Timer())

    assert output.update_pixels_calls == [("personal", output.created_buffers[0])]


def test_scene_prefix_unknown_effect_raises_with_effect_name_in_message(scene_env) -> None:
    scene_dir = _make_scene_dir(scene_env, "forest")
    _make_effects_subdir(scene_dir, {"flash": _stub_effect_source()})

    registry = SceneRegistry()
    registry.scan_dir(str(scene_env), MODULE_PREFIX)

    scene = registry.get("forest")
    manager = _make_effect_manager()
    manager.set_local_effects(scene.local_effect_registry)

    with pytest.raises(ValueError, match="missing_effect"):
        manager.set_effect(Scope.PERSONAL, "scene.missing_effect", {})


def test_scene_prefix_fires_start_event_with_pack_equals_scene(scene_env) -> None:
    scene_dir = _make_scene_dir(scene_env, "forest")
    _make_effects_subdir(scene_dir, {"flash": _stub_effect_source()})

    registry = SceneRegistry()
    registry.scan_dir(str(scene_env), MODULE_PREFIX)

    scene = registry.get("forest")
    output = SpyEffectOutput(min_resolution=16, scopes=[Scope.PERSONAL])
    manager = EffectManager(registry=PackRegistry(item_attr="BUILD"), outputs=[output])
    manager.set_local_effects(scene.local_effect_registry)

    receipt = manager.set_effect(Scope.PERSONAL, "scene.flash", {})

    assert output.handle_event_calls == [
        (EffectEvent("scene", "flash", "start"), frozenset({"personal"}), ANY, receipt)
    ]


# ---------------------------------------------------------------------------
# SceneManager pushes local effect registry on transitions
# ---------------------------------------------------------------------------


def test_scene_manager_pushes_local_effects_on_load(scene_env) -> None:
    scene_dir = _make_scene_dir(scene_env, "forest")
    _make_effects_subdir(scene_dir, {"flash": _stub_effect_source()})

    scene_registry = SceneRegistry()
    scene_registry.scan_dir(str(scene_env), MODULE_PREFIX)

    engine = GameEngine(effect_controls=_RecordingEffectControls())
    effect_admin = SpyEffectAdmin()
    manager = SceneManager(
        engine,
        PackRegistry(item_attr="BUILD"),
        PackRegistry(item_attr="RULE"),
        scene_registry,
        effect_admin,
    )
    manager.load("forest")
    manager.update()

    assert len(effect_admin.local_effects_history) == 1
    pushed = effect_admin.local_effects_history[0]
    assert isinstance(pushed, SceneLocalRegistry)
    assert "flash" in pushed.items()


def test_scene_manager_load_replaces_active_scene_registry_with_new_scenes(scene_env) -> None:
    """When load replaces the current scene, the new scene's registry is pushed once."""
    _make_scene_dir(scene_env, "a")
    _make_scene_dir(scene_env, "b")

    scene_registry = SceneRegistry()
    scene_registry.scan_dir(str(scene_env), MODULE_PREFIX)

    engine = GameEngine(effect_controls=_RecordingEffectControls())
    effect_admin = SpyEffectAdmin()
    manager = SceneManager(
        engine,
        PackRegistry(item_attr="BUILD"),
        PackRegistry(item_attr="RULE"),
        scene_registry,
        effect_admin,
    )

    manager.load("a")
    manager.update()
    effect_admin.local_effects_history.clear()

    manager.load("b")
    manager.update()

    # One push: the new scene b's (empty) local effect registry
    assert len(effect_admin.local_effects_history) == 1


def test_scene_manager_pushes_overlay_scene_local_effects_on_overlay(scene_env) -> None:
    scene_dir_b = _make_scene_dir(scene_env, "scene_b")
    _make_effects_subdir(scene_dir_b, {"b_flash": _stub_effect_source()})
    _make_scene_dir(scene_env, "scene_a")

    scene_registry = SceneRegistry()
    scene_registry.scan_dir(str(scene_env), MODULE_PREFIX)

    engine = GameEngine(effect_controls=_RecordingEffectControls())
    effect_admin = SpyEffectAdmin()
    manager = SceneManager(
        engine,
        PackRegistry(item_attr="BUILD"),
        PackRegistry(item_attr="RULE"),
        scene_registry,
        effect_admin,
    )

    manager.load("scene_a")
    manager.update()
    effect_admin.local_effects_history.clear()

    manager.overlay("scene_b")
    manager.update()

    assert len(effect_admin.local_effects_history) == 1
    pushed = effect_admin.local_effects_history[0]
    assert "b_flash" in pushed.items()


def test_scene_manager_restores_base_local_effects_on_pop(scene_env) -> None:
    scene_dir_a = _make_scene_dir(scene_env, "scene_a")
    _make_effects_subdir(scene_dir_a, {"a_flash": _stub_effect_source()})
    scene_dir_b = _make_scene_dir(scene_env, "scene_b")
    _make_effects_subdir(scene_dir_b, {"b_flash": _stub_effect_source()})

    scene_registry = SceneRegistry()
    scene_registry.scan_dir(str(scene_env), MODULE_PREFIX)

    engine = GameEngine(effect_controls=_RecordingEffectControls())
    effect_admin = SpyEffectAdmin()
    manager = SceneManager(
        engine,
        PackRegistry(item_attr="BUILD"),
        PackRegistry(item_attr="RULE"),
        scene_registry,
        effect_admin,
    )

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
# Isolation: scene-local effect not reachable from another scene
# ---------------------------------------------------------------------------


def test_loading_scene_b_after_a_does_not_expose_scene_a_locals(scene_env) -> None:
    scene_dir_a = _make_scene_dir(scene_env, "scene_a")
    _make_effects_subdir(scene_dir_a, {"secret": _stub_effect_source()})
    _make_scene_dir(scene_env, "scene_b")

    scene_registry = SceneRegistry()
    scene_registry.scan_dir(str(scene_env), MODULE_PREFIX)

    output = SpyEffectOutput(min_resolution=16, scopes=[Scope.PERSONAL])
    manager = EffectManager(registry=PackRegistry(item_attr="BUILD"), outputs=[output])

    scene_b = scene_registry.get("scene_b")
    manager.set_local_effects(scene_b.local_effect_registry)

    with pytest.raises(ValueError):
        manager.set_effect(Scope.PERSONAL, "scene.secret", {})


# ---------------------------------------------------------------------------
# Overlay replace semantics: B's locals only; A's unreachable while B on top
# ---------------------------------------------------------------------------


def test_overlay_b_on_a_resolves_scene_prefix_against_b_locals_only(scene_env) -> None:
    """With B overlaid on A, scene.* resolves against B's locals only."""
    scene_dir_a = _make_scene_dir(scene_env, "scene_a")
    _make_effects_subdir(scene_dir_a, {"a_only": _stub_effect_source()})
    scene_dir_b = _make_scene_dir(scene_env, "scene_b")
    _make_effects_subdir(scene_dir_b, {"b_only": _stub_effect_source()})

    scene_registry = SceneRegistry()
    scene_registry.scan_dir(str(scene_env), MODULE_PREFIX)

    output = SpyEffectOutput(min_resolution=16, scopes=[Scope.PERSONAL])
    manager = EffectManager(registry=PackRegistry(item_attr="BUILD"), outputs=[output])

    # Simulate B overlaid on A: push B's locals
    scene_b = scene_registry.get("scene_b")
    manager.set_local_effects(scene_b.local_effect_registry)

    # A's local 'a_only' must not be reachable from B's context
    with pytest.raises(ValueError, match="a_only"):
        manager.set_effect(Scope.PERSONAL, "scene.a_only", {})


def test_overlay_b_on_a_after_pop_a_locals_restored(scene_env) -> None:
    """After B pops, A's locals are reachable again."""
    scene_dir_a = _make_scene_dir(scene_env, "scene_a")
    _make_effects_subdir(scene_dir_a, {"a_only": _stub_effect_source()})
    scene_dir_b = _make_scene_dir(scene_env, "scene_b")
    _make_effects_subdir(scene_dir_b, {"b_only": _stub_effect_source()})

    scene_registry = SceneRegistry()
    scene_registry.scan_dir(str(scene_env), MODULE_PREFIX)

    output = SpyEffectOutput(min_resolution=16, scopes=[Scope.PERSONAL])
    manager = EffectManager(registry=PackRegistry(item_attr="BUILD"), outputs=[output])

    # Simulate B overlaid then popped — A restored
    scene_a = scene_registry.get("scene_a")
    manager.set_local_effects(scene_a.local_effect_registry)

    # A's local effect must resolve successfully after restore
    receipt = manager.set_effect(Scope.PERSONAL, "scene.a_only", {})
    assert receipt is not None


# ---------------------------------------------------------------------------
# PackRegistry.scan_dir — 'scene' is a reserved pack name
# ---------------------------------------------------------------------------


def test_pack_registry_scan_dir_raises_for_pack_named_scene(tmp_path) -> None:
    scene_pack_dir = tmp_path / "scene"
    scene_pack_dir.mkdir()
    (scene_pack_dir / "version.txt").write_text("1.0\n")

    registry = PackRegistry(item_attr="BUILD")

    with pytest.raises(ValueError, match="reserved"):
        registry.scan_dir(str(tmp_path), "tp")


def test_pack_registry_scan_dir_raises_for_rule_pack_named_scene(tmp_path) -> None:
    scene_pack_dir = tmp_path / "scene"
    scene_pack_dir.mkdir()
    (scene_pack_dir / "version.txt").write_text("1.0\n")

    registry = PackRegistry(item_attr="RULE")

    with pytest.raises(ValueError, match="reserved"):
        registry.scan_dir(str(tmp_path), "tp")


def test_pack_registry_scan_dir_non_reserved_pack_name_is_discovered_normally(
    tmp_path,
) -> None:
    """A pack directory not named 'scene' scans without error."""
    good_pack_dir = tmp_path / "elements"
    good_pack_dir.mkdir()
    (good_pack_dir / "version.txt").write_text("1.0\n")
    (good_pack_dir / "fire.py").write_text("")

    registry = PackRegistry(item_attr="BUILD")
    registry.scan_dir(str(tmp_path), "tp")

    assert "fire" in registry.items("elements")


# ---------------------------------------------------------------------------
# EffectEvent.pack == "scene" for scene-local effects
# ---------------------------------------------------------------------------


def test_effect_event_pack_is_scene_for_scene_local_effect(scene_env) -> None:
    scene_dir = _make_scene_dir(scene_env, "forest")
    _make_effects_subdir(scene_dir, {"flash": _stub_effect_source()})

    scene_reg = SceneRegistry()
    scene_reg.scan_dir(str(scene_env), MODULE_PREFIX)
    scene = scene_reg.get("forest")

    output = SpyEffectOutput(min_resolution=16, scopes=[Scope.PERSONAL])
    manager = EffectManager(registry=PackRegistry(item_attr="BUILD"), outputs=[output])
    manager.set_local_effects(scene.local_effect_registry)

    manager.set_effect(Scope.PERSONAL, "scene.flash", {})

    start_event = output.handle_event_calls[0][0]
    assert start_event.pack == "scene"
    assert start_event.name == "flash"
