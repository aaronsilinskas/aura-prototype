"""Tests for SceneRegistry.scan_dir(path, module_prefix) — new required parameter,
rules/ subdir detection, and SceneManager rule resolution with scene-local rules.
"""

from __future__ import annotations

import json
import sys

import pytest

from engine.engine import GameEngine, GameRule
from engine.events import Event, EventGroup
from engine.packs import PackRegistry
from engine.scene import Scene, SceneManager, SceneRegistry
from engine.state import EffectControls

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_GROUP = EventGroup("test")
MODULE_PREFIX = "tsd"


@pytest.fixture()
def scene_env(tmp_path):
    """Yield a ``tsd/`` subdirectory of tmp_path as the scenes root.

    ``tmp_path`` is inserted into ``sys.path`` so scene-local rule modules of
    the form ``tsd.<scene>.rules.<item>`` resolve to the real files created by
    tests.  All imported modules added during the test are removed on teardown.
    """
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


def _make_scene_dir(root, name: str, **json_overrides) -> None:
    scene_dir = root / name
    scene_dir.mkdir(parents=True, exist_ok=True)
    _write_scene_json(scene_dir, _minimal_scene_json(**json_overrides))


def _rule_source(class_name: str = "ARule") -> str:
    return (
        "from engine.engine import GameRule\n"
        "class " + class_name + "(GameRule): pass\n"
        "RULE = " + class_name + "()\n"
    )


def _make_rules_subdir(scene_dir, items: dict[str, str]) -> None:
    """Create a rules/ subdir under *scene_dir* with .py item files."""
    rules_dir = scene_dir / "rules"
    rules_dir.mkdir(exist_ok=True)
    for name, content in items.items():
        (rules_dir / (name + ".py")).write_text(content)


# ---------------------------------------------------------------------------
# scan_dir — module_prefix is now a required parameter
# ---------------------------------------------------------------------------


def test_scan_dir_discovers_scenes_when_called_with_module_prefix(scene_env) -> None:
    _make_scene_dir(scene_env, "forest")
    registry = SceneRegistry()

    # Should not raise
    registry.scan_dir(str(scene_env), MODULE_PREFIX)

    assert "forest" in registry.names()


def test_scan_dir_idempotent_with_module_prefix(scene_env) -> None:
    _make_scene_dir(scene_env, "forest")
    registry = SceneRegistry()

    registry.scan_dir(str(scene_env), MODULE_PREFIX)
    registry.scan_dir(str(scene_env), MODULE_PREFIX)

    assert registry.names() == ["forest"]


# ---------------------------------------------------------------------------
# scan_dir — rules/ subdir detection
# ---------------------------------------------------------------------------


def test_scan_dir_exposes_rules_subdir_items_via_local_rule_registry(scene_env) -> None:
    scene_dir = scene_env / "forest"
    _make_scene_dir(scene_env, "forest")
    _make_rules_subdir(scene_dir, {"ambush": _rule_source("Ambush")})

    registry = SceneRegistry()
    registry.scan_dir(str(scene_env), MODULE_PREFIX)

    scene = registry.get("forest")
    assert "ambush" in scene.local_rule_registry.items()


def test_scan_dir_scene_with_no_rules_subdir_has_empty_local_rule_registry(
    scene_env,
) -> None:
    _make_scene_dir(scene_env, "empty_scene")
    registry = SceneRegistry()
    registry.scan_dir(str(scene_env), MODULE_PREFIX)

    scene = registry.get("empty_scene")
    assert scene.local_rule_registry.items() == []


def test_scan_dir_excludes_init_py_from_rule_item_names(scene_env) -> None:
    scene_dir = scene_env / "forest"
    _make_scene_dir(scene_env, "forest")
    rules_dir = scene_dir / "rules"
    rules_dir.mkdir()
    (rules_dir / "__init__.py").write_text("")
    (rules_dir / "my_rule.py").write_text(_rule_source())

    registry = SceneRegistry()
    registry.scan_dir(str(scene_env), MODULE_PREFIX)

    scene = registry.get("forest")
    assert "__init__" not in scene.local_rule_registry.items()
    assert "my_rule" in scene.local_rule_registry.items()


def test_scan_dir_excludes_tests_subdir_from_rule_item_names(scene_env) -> None:
    scene_dir = scene_env / "forest"
    _make_scene_dir(scene_env, "forest")
    rules_dir = scene_dir / "rules"
    rules_dir.mkdir()
    (rules_dir / "my_rule.py").write_text(_rule_source())
    tests_dir = rules_dir / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_my_rule.py").write_text("")

    registry = SceneRegistry()
    registry.scan_dir(str(scene_env), MODULE_PREFIX)

    scene = registry.get("forest")
    assert "tests" not in scene.local_rule_registry.items()
    assert "my_rule" in scene.local_rule_registry.items()


def test_scan_dir_ignores_helper_subpackages_in_rules_dir(scene_env) -> None:
    scene_dir = scene_env / "forest"
    _make_scene_dir(scene_env, "forest")
    rules_dir = scene_dir / "rules"
    rules_dir.mkdir()
    (rules_dir / "my_rule.py").write_text(_rule_source())
    helper_dir = rules_dir / "helpers"
    helper_dir.mkdir()
    (helper_dir / "util.py").write_text("")

    registry = SceneRegistry()
    registry.scan_dir(str(scene_env), MODULE_PREFIX)

    scene = registry.get("forest")
    assert "helpers" not in scene.local_rule_registry.items()
    assert "my_rule" in scene.local_rule_registry.items()


def test_scene_constructed_directly_has_empty_local_rule_registry() -> None:
    scene = Scene(effect_packs=[], rule_packs=[])

    assert scene.local_rule_registry.items() == []


def test_scan_dir_local_registry_shared_across_fresh_scene_instances(scene_env) -> None:
    scene_dir = scene_env / "forest"
    _make_scene_dir(scene_env, "forest")
    _make_rules_subdir(scene_dir, {"my_rule": _rule_source()})

    registry = SceneRegistry()
    registry.scan_dir(str(scene_env), MODULE_PREFIX)

    scene_a = registry.get("forest")
    scene_b = registry.get("forest")

    assert scene_a.local_rule_registry is scene_b.local_rule_registry


def test_scan_dir_local_rules_not_visible_to_other_scene(scene_env) -> None:
    scene_a_dir = scene_env / "forest"
    _make_scene_dir(scene_env, "forest")
    _make_rules_subdir(scene_a_dir, {"secret_rule": _rule_source()})
    _make_scene_dir(scene_env, "cave")

    registry = SceneRegistry()
    registry.scan_dir(str(scene_env), MODULE_PREFIX)

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


def test_scene_manager_load_includes_scene_local_rules_in_engine(scene_env) -> None:
    scene_dir = scene_env / "my_scene"
    _make_scene_dir(scene_env, "my_scene")
    _make_rules_subdir(scene_dir, {"local_rule": _rule_source("LocalRule")})

    scene_registry = SceneRegistry()
    scene_registry.scan_dir(str(scene_env), MODULE_PREFIX)

    engine = _make_engine()
    manager = SceneManager(
        engine,
        PackRegistry(item_attr="BUILD"),
        PackRegistry(item_attr="RULE"),
        scene_registry,
    )
    manager.load("my_scene")
    manager.update()

    assert len(engine.rules) == 1
    assert isinstance(engine.rules[0], GameRule)


def test_scene_manager_load_appends_local_rules_after_pack_rules(scene_env) -> None:
    """Local rules come after pack rules in the engine's rule list."""
    from engine.packs import PackRegistry as PR
    from engine.packs import _PackEntry
    from engine.version import Version

    class _TestPackRegistry(PR):
        def register_instance(self, pack_name, item_name, instance, version="1.0"):
            if pack_name not in self._packs:
                self._packs[pack_name] = _PackEntry(
                    name=pack_name,
                    version=Version.parse(version),
                    module_prefix="",
                    item_names={item_name},
                    source_path="",
                )
            else:
                self._packs[pack_name].item_names.add(item_name)
            self._cache[(pack_name, item_name)] = instance

    pack_rule = GameRule()
    rule_registry = _TestPackRegistry(item_attr="RULE")
    rule_registry.register_instance("pack_rules", "pack_rule", pack_rule)

    scene_dir = scene_env / "my_scene"
    _make_scene_dir(scene_env, "my_scene", rule_packs=[["pack_rules", "1.0"]])
    _make_rules_subdir(scene_dir, {"local_rule": _rule_source("LocalRule")})

    scene_registry = SceneRegistry()
    scene_registry.scan_dir(str(scene_env), MODULE_PREFIX)

    engine = _make_engine()
    manager = SceneManager(
        engine,
        PackRegistry(item_attr="BUILD"),
        rule_registry,
        scene_registry,
    )
    manager.load("my_scene")
    manager.update()

    rules = engine.rules
    assert len(rules) == 2
    # pack rule first, local rule second
    assert rules[0] is pack_rule
    assert isinstance(rules[1], GameRule)
    assert rules[1] is not pack_rule


def test_scene_manager_local_rule_missing_rule_attr_fails_at_scene_load(
    scene_env,
) -> None:
    scene_dir = scene_env / "my_scene"
    _make_scene_dir(scene_env, "my_scene")
    _make_rules_subdir(scene_dir, {"broken_rule": "NOT_A_RULE = 1"})

    scene_registry = SceneRegistry()
    scene_registry.scan_dir(str(scene_env), MODULE_PREFIX)

    engine = _make_engine()
    manager = SceneManager(
        engine,
        PackRegistry(item_attr="BUILD"),
        PackRegistry(item_attr="RULE"),
        scene_registry,
    )
    manager.load("my_scene")

    with pytest.raises(ValueError, match="no attribute 'RULE'"):
        manager.update()


def test_scene_manager_local_rules_are_not_active_for_other_loaded_scene(
    scene_env,
) -> None:
    scene_a_dir = scene_env / "scene_a"
    _make_scene_dir(scene_env, "scene_a")
    _make_rules_subdir(scene_a_dir, {"local_rule": _rule_source("LocalRule")})
    _make_scene_dir(scene_env, "scene_b")

    scene_registry = SceneRegistry()
    scene_registry.scan_dir(str(scene_env), MODULE_PREFIX)

    engine = _make_engine()
    manager = SceneManager(
        engine,
        PackRegistry(item_attr="BUILD"),
        PackRegistry(item_attr="RULE"),
        scene_registry,
    )

    # Load scene_b — should have no rules (scene_a's local rule must not bleed in)
    manager.load("scene_b")
    manager.update()

    assert engine.rules == []


def test_local_rule_receives_events_after_scene_load(scene_env) -> None:
    scene_dir = scene_env / "my_scene"
    _make_scene_dir(scene_env, "my_scene")
    # Write a rule that records received events
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
    _make_rules_subdir(scene_dir, {"recorder": rule_src})

    scene_registry = SceneRegistry()
    scene_registry.scan_dir(str(scene_env), MODULE_PREFIX)

    engine = _make_engine()
    manager = SceneManager(
        engine,
        PackRegistry(item_attr="BUILD"),
        PackRegistry(item_attr="RULE"),
        scene_registry,
    )
    manager.load("my_scene")
    manager.update()
    manager.update()  # first engine tick

    manager.active_state.queue_event(Event(_GROUP, "ping"))
    manager.update()

    rule = engine.rules[0]
    assert "ping" in rule.received
