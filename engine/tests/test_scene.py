from __future__ import annotations

import sys

import pytest

from engine.packs import PackRegistry
from engine.scene import Scene, SceneControls, SceneManager

MODULE_PREFIX = "tp_scene"


class _SpyState:
    __slots__ = ("clear_calls", "data", "effect_controls", "scene_controls")

    def __init__(
        self,
        effect_controls: object,
        scene_controls: SceneControls,
        data: dict | None,
    ) -> None:
        self.effect_controls = effect_controls
        self.scene_controls = scene_controls
        self.data = {} if data is None else data
        self.clear_calls = 0

    def clear_queue(self) -> None:
        self.clear_calls += 1


class _SpyEngine:
    __slots__ = ("created_states", "effect_controls", "last_rules", "update_calls")

    def __init__(self) -> None:
        self.effect_controls = object()
        self.created_states: list[_SpyState] = []
        self.last_rules: list[object] = []
        self.update_calls: list[_SpyState] = []

    def create_state(
        self, scene_controls: SceneControls, initial_data: dict | None = None
    ) -> _SpyState:
        state = _SpyState(self.effect_controls, scene_controls, initial_data)
        self.created_states.append(state)
        return state

    def set_rules(self, rules: list[object]) -> None:
        self.last_rules = list(rules)

    def update(self, state: _SpyState) -> None:
        self.update_calls.append(state)


@pytest.fixture()
def pack_env(tmp_path):
    packs_root = tmp_path / MODULE_PREFIX
    packs_root.mkdir()
    sys.path.insert(0, str(tmp_path))
    known_modules = set(sys.modules)
    yield packs_root
    for key in list(sys.modules):
        if key not in known_modules:
            del sys.modules[key]
    sys.path.remove(str(tmp_path))


def _make_pack(root, pack_name: str, version: str, items: dict[str, str]) -> None:
    pack_dir = root / pack_name
    pack_dir.mkdir(parents=True, exist_ok=True)
    (pack_dir / "__init__.py").write_text("")
    (pack_dir / "version.txt").write_text(version + "\n")
    for item_name, content in items.items():
        (pack_dir / (item_name + ".py")).write_text(content)


def _make_registry() -> PackRegistry:
    return PackRegistry(extractor=lambda module: module)


def _make_manager(
    effect_registry: PackRegistry, rule_registry: PackRegistry
) -> tuple[_SpyEngine, SceneManager]:
    engine = _SpyEngine()
    return engine, SceneManager(engine, effect_registry, rule_registry)


def test_scene_controls_default_methods_raise_and_slots_exist() -> None:
    controls = SceneControls()
    assert SceneControls.__slots__ == ()
    with pytest.raises(NotImplementedError):
        controls.load("x")
    with pytest.raises(NotImplementedError):
        controls.overlay("x")
    with pytest.raises(NotImplementedError):
        controls.pop()


def test_scene_uses_slots_and_stores_all_fields() -> None:
    scene = Scene(
        rules=["r"],
        effect_packs=[("fx", "1.0")],
        rule_packs=[("rp", "1.0")],
        initial_data={"x": 1},
    )
    assert scene.rules == ["r"]
    assert scene.effect_packs == [("fx", "1.0")]
    assert scene.rule_packs == [("rp", "1.0")]
    assert scene.initial_data == {"x": 1}
    with pytest.raises(AttributeError):
        scene.extra = 1  # type: ignore[attr-defined]


def test_update_applies_only_last_pending_transition_end_of_tick(pack_env) -> None:
    _make_pack(pack_env, "effect_pack", "1.0", {})
    effect_registry = _make_registry()
    effect_registry.scan_dir(str(pack_env), MODULE_PREFIX)
    rule_registry = _make_registry()
    rule_registry.scan_dir(str(pack_env), MODULE_PREFIX)
    engine, manager = _make_manager(effect_registry, rule_registry)
    events: list[str] = []
    manager.register("a", lambda: Scene([], [], [], on_load=lambda _: events.append("load:a")))
    manager.register("b", lambda: Scene([], [], [], on_load=lambda _: events.append("load:b")))

    manager.load("a")
    manager.load("b")
    assert events == []

    manager.update()
    assert events == ["load:b"]
    assert len(engine.update_calls) == 0

    manager.update()
    assert len(engine.update_calls) == 1


def test_load_overlay_pop_validation_happens_before_state_changes(pack_env) -> None:
    _make_pack(pack_env, "effect_pack", "1.0", {})
    effect_registry = _make_registry()
    effect_registry.scan_dir(str(pack_env), MODULE_PREFIX)
    rule_registry = _make_registry()
    rule_registry.scan_dir(str(pack_env), MODULE_PREFIX)
    engine, manager = _make_manager(effect_registry, rule_registry)
    manager.register("base", lambda: Scene([], [], []))

    with pytest.raises(ValueError, match="Unknown scene"):
        manager.load("missing")
    with pytest.raises(ValueError, match="empty stack"):
        manager.overlay("base")

    manager.load("base")
    manager.update()

    with pytest.raises(ValueError, match="fewer than 2"):
        manager.pop()
    with pytest.raises(ValueError, match="Unknown scene"):
        manager.overlay("missing")
    assert len(engine.created_states) == 1


def test_load_validates_packs_before_unloading_current_scene(pack_env) -> None:
    _make_pack(pack_env, "effect_pack", "1.0", {})
    effect_registry = _make_registry()
    effect_registry.scan_dir(str(pack_env), MODULE_PREFIX)
    rule_registry = _make_registry()
    rule_registry.scan_dir(str(pack_env), MODULE_PREFIX)
    engine, manager = _make_manager(effect_registry, rule_registry)
    events: list[str] = []
    manager.register(
        "ok", lambda: Scene([], [], [], on_unload=lambda _: events.append("unload:ok"))
    )
    manager.register("bad", lambda: Scene([], [("effect_pack", "1.1")], []))

    manager.load("ok")
    manager.update()

    with pytest.raises(ValueError, match="upgrade the pack"):
        manager.load("bad")

    assert events == []
    assert len(engine.created_states) == 1


def test_overlay_validates_before_suspend(pack_env) -> None:
    _make_pack(pack_env, "effect_pack", "1.0", {})
    effect_registry = _make_registry()
    effect_registry.scan_dir(str(pack_env), MODULE_PREFIX)
    rule_registry = _make_registry()
    rule_registry.scan_dir(str(pack_env), MODULE_PREFIX)
    engine, manager = _make_manager(effect_registry, rule_registry)
    events: list[str] = []
    manager.register(
        "base", lambda: Scene([], [], [], on_suspend=lambda _: events.append("suspend:base"))
    )
    manager.register("bad", lambda: Scene([], [("effect_pack", "2.0")], []))

    manager.load("base")
    manager.update()

    with pytest.raises(ValueError, match="incompatible"):
        manager.overlay("bad")

    assert events == []
    assert len(engine.created_states) == 1


def test_load_clears_stack_top_down_and_calls_lifecycle_callbacks(pack_env) -> None:
    _make_pack(pack_env, "effect_pack", "1.0", {})
    effect_registry = _make_registry()
    effect_registry.scan_dir(str(pack_env), MODULE_PREFIX)
    rule_registry = _make_registry()
    rule_registry.scan_dir(str(pack_env), MODULE_PREFIX)
    engine, manager = _make_manager(effect_registry, rule_registry)
    events: list[str] = []
    manager.register(
        "base",
        lambda: Scene(
            [],
            [],
            [],
            on_unload=lambda _: events.append("unload:base"),
            on_suspend=lambda _: events.append("suspend:base"),
        ),
    )
    manager.register(
        "overlay",
        lambda: Scene([], [], [], on_unload=lambda _: events.append("unload:overlay")),
    )
    manager.register(
        "replacement",
        lambda: Scene([], [], [], on_load=lambda _: events.append("load:replacement")),
    )

    manager.load("base")
    manager.update()
    manager.overlay("overlay")
    manager.update()
    manager.load("replacement")
    manager.update()

    assert events == ["suspend:base", "unload:overlay", "unload:base", "load:replacement"]
    assert len(engine.created_states) == 3
    assert engine.created_states[0].clear_calls == 1
    assert engine.created_states[1].clear_calls == 1


def test_pop_restores_cached_rules_clears_queues_and_calls_resume(pack_env) -> None:
    _make_pack(pack_env, "effect_pack", "1.0", {})
    _make_pack(
        pack_env,
        "rules_pack",
        "1.0",
        {
            "alpha": "RULE = 'ALPHA'\n",
            "beta": "RULE = 'BETA'\n",
        },
    )
    effect_registry = _make_registry()
    effect_registry.scan_dir(str(pack_env), MODULE_PREFIX)
    rule_registry = _make_registry()
    rule_registry.scan_dir(str(pack_env), MODULE_PREFIX)
    engine, manager = _make_manager(effect_registry, rule_registry)
    events: list[str] = []
    manager.register(
        "base",
        lambda: Scene(
            ["BASE"],
            [],
            [("rules_pack", "1.0")],
            on_resume=lambda _: events.append("resume:base"),
        ),
    )
    manager.register(
        "overlay",
        lambda: Scene(["OVERLAY"], [], [], on_unload=lambda _: events.append("unload:overlay")),
    )

    manager.load("base")
    manager.update()
    assert engine.last_rules == ["BASE", "ALPHA", "BETA"]

    manager.overlay("overlay")
    manager.update()
    assert engine.last_rules == ["OVERLAY"]

    manager.pop()
    manager.update()
    assert engine.last_rules == ["BASE", "ALPHA", "BETA"]
    assert events == ["unload:overlay", "resume:base"]
    assert engine.created_states[0].clear_calls == 2
    assert engine.created_states[1].clear_calls == 1


def test_rule_modules_must_export_uppercase_rule(pack_env) -> None:
    _make_pack(pack_env, "effect_pack", "1.0", {})
    _make_pack(pack_env, "rules_bad", "1.0", {"broken": "rule = object()\n"})
    effect_registry = _make_registry()
    effect_registry.scan_dir(str(pack_env), MODULE_PREFIX)
    rule_registry = _make_registry()
    rule_registry.scan_dir(str(pack_env), MODULE_PREFIX)
    _, manager = _make_manager(effect_registry, rule_registry)
    manager.register("bad", lambda: Scene([], [], [("rules_bad", "1.0")]))
    manager.load("bad")

    with pytest.raises(ValueError, match="must export RULE"):
        manager.update()
