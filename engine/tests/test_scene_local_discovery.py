"""Tests for scene-local rule discovery through ``scan_pack_roots`` (the rules/
subdir of each scanned scene) and SceneManager rule resolution with scene-local rules.
"""

from __future__ import annotations

import pytest

from engine.engine import GameEngine, GameRule
from engine.events import Event, EventGroup
from engine.pack_catalog import PackCatalog, scan_pack_roots
from engine.scene import Scene, SceneManager
from engine.state import EffectControls
from engine.tests.helpers import RecordingSceneReboot, SpyAudioOverlayAdmin, SpyEffectAdmin

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_GROUP = EventGroup("test")
ROOT_NAME = "tsd_flash"


def _rule_source(class_name: str = "ARule") -> str:
    return (
        "from engine.engine import GameRule\n"
        "class " + class_name + "(GameRule): pass\n"
        "RULE = " + class_name + "()\n"
    )


# ---------------------------------------------------------------------------
# rules/ folder discovery
# ---------------------------------------------------------------------------


def test_a_scenes_rules_folder_items_are_its_local_rules(pack_tree) -> None:
    root = pack_tree.root(ROOT_NAME)
    pack_tree.scene(root, "forest", rules={"ambush": _rule_source("Ambush")})

    registry = scan_pack_roots([str(root)]).scene_registry

    scene = registry.get("forest")
    assert "ambush" in scene.local_rule_registry.items()


def test_a_scene_without_a_rules_folder_has_an_empty_local_rule_registry(pack_tree) -> None:
    root = pack_tree.root(ROOT_NAME)
    pack_tree.scene(root, "empty_scene")

    registry = scan_pack_roots([str(root)]).scene_registry

    scene = registry.get("empty_scene")
    assert scene.local_rule_registry.items() == []


def test_init_py_is_not_a_local_rule(pack_tree) -> None:
    root = pack_tree.root(ROOT_NAME)
    scene_dir = pack_tree.scene(root, "forest", rules={"my_rule": _rule_source()})
    (scene_dir / "rules" / "__init__.py").write_text("")

    registry = scan_pack_roots([str(root)]).scene_registry

    scene = registry.get("forest")
    assert "__init__" not in scene.local_rule_registry.items()
    assert "my_rule" in scene.local_rule_registry.items()


def test_a_tests_subfolder_of_the_rules_folder_is_not_a_local_rule(pack_tree) -> None:
    root = pack_tree.root(ROOT_NAME)
    scene_dir = pack_tree.scene(root, "forest", rules={"my_rule": _rule_source()})
    tests_dir = scene_dir / "rules" / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_my_rule.py").write_text("")

    registry = scan_pack_roots([str(root)]).scene_registry

    scene = registry.get("forest")
    assert "tests" not in scene.local_rule_registry.items()
    assert "my_rule" in scene.local_rule_registry.items()


def test_a_helper_subpackage_of_the_rules_folder_is_not_a_local_rule(pack_tree) -> None:
    root = pack_tree.root(ROOT_NAME)
    scene_dir = pack_tree.scene(root, "forest", rules={"my_rule": _rule_source()})
    helper_dir = scene_dir / "rules" / "helpers"
    helper_dir.mkdir()
    (helper_dir / "util.py").write_text("")

    registry = scan_pack_roots([str(root)]).scene_registry

    scene = registry.get("forest")
    assert "helpers" not in scene.local_rule_registry.items()
    assert "my_rule" in scene.local_rule_registry.items()


def test_scene_constructed_directly_has_empty_local_rule_registry() -> None:
    scene = Scene(effect_packs=[], rule_packs=[])

    assert scene.local_rule_registry.items() == []


def test_each_fresh_scene_shares_one_local_rule_registry(pack_tree) -> None:
    root = pack_tree.root(ROOT_NAME)
    pack_tree.scene(root, "forest", rules={"my_rule": _rule_source()})

    registry = scan_pack_roots([str(root)]).scene_registry

    scene_a = registry.get("forest")
    scene_b = registry.get("forest")

    assert scene_a.local_rule_registry is scene_b.local_rule_registry


def test_a_scenes_local_rules_are_not_visible_to_another_scene(pack_tree) -> None:
    root = pack_tree.root(ROOT_NAME)
    pack_tree.scene(root, "forest", rules={"secret_rule": _rule_source()})
    pack_tree.scene(root, "cave")

    registry = scan_pack_roots([str(root)]).scene_registry

    cave_scene = registry.get("cave")
    assert "secret_rule" not in cave_scene.local_rule_registry.items()


# ---------------------------------------------------------------------------
# SceneManager — scene-local rules appended after pack rules on load
# ---------------------------------------------------------------------------


class _RecordingEffectControls(EffectControls):
    def stop_effect(self, scope) -> None:
        pass


def _make_engine() -> GameEngine:
    return GameEngine(effect_controls=_RecordingEffectControls())


def _make_scene_manager(engine: GameEngine, catalog: PackCatalog) -> SceneManager:
    """Construct a SceneManager with a SpyEffectAdmin/SpyAudioOverlayAdmin — these tests
    only cover scene-local rule discovery, not local-effects/merge-strategy/audio-overlay
    transitions."""
    return SceneManager(
        engine,
        catalog.effect_registry,
        catalog.rule_registry,
        catalog.scene_registry,
        SpyEffectAdmin(),
        SpyAudioOverlayAdmin(),
        RecordingSceneReboot(),
    )


def test_scene_manager_load_includes_scene_local_rules_in_engine(pack_tree) -> None:
    root = pack_tree.root(ROOT_NAME)
    pack_tree.scene(root, "my_scene", rules={"local_rule": _rule_source("LocalRule")})

    engine = _make_engine()
    manager = _make_scene_manager(engine, scan_pack_roots([str(root)]))
    manager.load("my_scene")
    manager.update()

    assert len(engine.rules) == 1
    assert isinstance(engine.rules[0], GameRule)


def test_scene_manager_load_appends_local_rules_after_pack_rules(pack_tree) -> None:
    """Local rules come after pack rules in the engine's rule list."""
    root = pack_tree.root(ROOT_NAME)
    pack_tree.rule_pack(root, "pack_rules", items={"pack_rule": _rule_source("PackRule")})
    pack_tree.scene(
        root,
        "my_scene",
        rule_packs=[["pack_rules", "1.0"]],
        rules={"local_rule": _rule_source("LocalRule")},
    )
    catalog = scan_pack_roots([str(root)])
    pack_rule = catalog.rule_registry.get("pack_rules", "pack_rule", GameRule)

    engine = _make_engine()
    manager = _make_scene_manager(engine, catalog)
    manager.load("my_scene")
    manager.update()

    rules = engine.rules
    assert len(rules) == 2
    # pack rule first, local rule second
    assert rules[0] is pack_rule
    assert isinstance(rules[1], GameRule)
    assert rules[1] is not pack_rule


def test_scene_manager_local_rule_missing_rule_attr_fails_at_scene_load(pack_tree) -> None:
    root = pack_tree.root(ROOT_NAME)
    pack_tree.scene(root, "my_scene", rules={"broken_rule": "NOT_A_RULE = 1"})

    engine = _make_engine()
    manager = _make_scene_manager(engine, scan_pack_roots([str(root)]))
    manager.load("my_scene")

    with pytest.raises(ValueError, match="no attribute 'RULE'"):
        manager.update()


def test_scene_manager_local_rules_are_not_active_for_other_loaded_scene(pack_tree) -> None:
    root = pack_tree.root(ROOT_NAME)
    pack_tree.scene(root, "scene_a", rules={"local_rule": _rule_source("LocalRule")})
    pack_tree.scene(root, "scene_b")

    engine = _make_engine()
    manager = _make_scene_manager(engine, scan_pack_roots([str(root)]))

    # Load scene_b — should have no rules (scene_a's local rule must not bleed in)
    manager.load("scene_b")
    manager.update()

    assert engine.rules == []


def test_local_rule_receives_events_after_scene_load(pack_tree) -> None:
    # A rule that records received events
    rule_src = (
        "from engine.engine import GameRule\n"
        "from engine.state import GameState\n"
        "from engine.events import Event\n"
        "\n"
        "class RecorderRule(GameRule):\n"
        "    def __init__(self):\n"
        "        self.received = []\n"
        "        self.on(Event, self._handle)\n"
        "    def _handle(self, event, state):\n"
        "        self.received.append(event.name)\n"
        "\n"
        "RULE = RecorderRule()\n"
    )
    root = pack_tree.root(ROOT_NAME)
    pack_tree.scene(root, "my_scene", rules={"recorder": rule_src})

    engine = _make_engine()
    manager = _make_scene_manager(engine, scan_pack_roots([str(root)]))
    manager.load("my_scene")
    manager.update()
    manager.update()  # first engine tick

    manager.active_state.queue_event(Event(_GROUP, "ping"))
    manager.update()

    rule = engine.rules[0]
    assert "ping" in rule.received
