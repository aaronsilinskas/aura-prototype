"""Tests for engine.scene: Scene, SceneControls, and SceneManager."""

from __future__ import annotations

import sys

import pytest

from engine.effects.manager import EffectManager
from engine.effects.merge import ADDITIVE, SPLIT
from engine.engine import GameEngine, GameRule
from engine.events import Event, EventGroup
from engine.packs import PackRegistry, _PackEntry
from engine.scene import Scene, SceneManager, SceneRegistry
from engine.state import EffectAdmin, EffectControls, GameState, SceneControls, Scope
from engine.tests.effects.helpers import SpyEffectOutput
from engine.tests.helpers import SpyEffectAdmin
from engine.timer import Timer
from engine.version import Version

# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

_GROUP = EventGroup("test")

MODULE_PREFIX = "tp_scene"


@pytest.fixture()
def pack_env(tmp_path):
    """Yield a packs root directory; insert into sys.path and clean up after."""
    packs_root = tmp_path / MODULE_PREFIX
    packs_root.mkdir()
    sys.path.insert(0, str(tmp_path))
    known_modules = set(sys.modules)
    yield packs_root
    for key in list(sys.modules):
        if key not in known_modules:
            del sys.modules[key]
    sys.path.remove(str(tmp_path))


def _make_rule_pack(root, pack_name: str, version: str, items: dict[str, str]) -> None:
    """Create a rule pack directory with RULE-exporting items under *root*."""
    pack_dir = root / pack_name
    pack_dir.mkdir(parents=True, exist_ok=True)
    (pack_dir / "version.txt").write_text(version + "\n")
    for item_name, content in items.items():
        (pack_dir / (item_name + ".py")).write_text(content)


def _make_effect_pack(root, pack_name: str, version: str) -> None:
    """Create a minimal effect pack directory with only version.txt."""
    pack_dir = root / pack_name
    pack_dir.mkdir(parents=True, exist_ok=True)
    (pack_dir / "version.txt").write_text(version + "\n")


def _make_color_effect_pack(root, pack_name: str) -> None:
    """Create an effect pack with solid-fill 'red' and 'blue' effects for merge-strategy tests."""
    pack_dir = root / pack_name
    pack_dir.mkdir(parents=True, exist_ok=True)
    (pack_dir / "version.txt").write_text("1.0\n")
    (pack_dir / "red.py").write_text(
        "from engine.tests.effects.helpers import ColorFillEffectBuilder\n"
        "BUILD = ColorFillEffectBuilder(0xFF0000)\n"
    )
    (pack_dir / "blue.py").write_text(
        "from engine.tests.effects.helpers import ColorFillEffectBuilder\n"
        "BUILD = ColorFillEffectBuilder(0x0000FF)\n"
    )


def _make_registries(pack_env_path: str):
    """Return (effect_registry, rule_registry) scanned from *pack_env_path*."""
    effect_registry = PackRegistry(item_attr="BUILD")
    rule_registry = _TestPackRegistry(item_attr="RULE")
    effect_registry.scan_dir(pack_env_path, MODULE_PREFIX)
    rule_registry.scan_dir(pack_env_path, MODULE_PREFIX)
    return effect_registry, rule_registry


class _RecordingEffectControls(EffectControls):
    """EffectControls that records stop_effect scopes.

    Local-effects pushes and merge-strategy lifecycle calls no longer go
    through ``EffectControls`` — see ``SpyEffectAdmin`` for those.
    """

    def __init__(self) -> None:
        self.stopped_scopes: list = []

    def stop_effect(self, scope) -> None:
        self.stopped_scopes.append(scope)


def _make_engine() -> GameEngine:
    return GameEngine(effect_controls=_RecordingEffectControls())


def _make_engine_with_controls():
    """Return (engine, recording_controls) so tests can inspect stopped scopes."""
    controls = _RecordingEffectControls()
    return GameEngine(effect_controls=controls), controls


def _make_scene_manager(
    engine: GameEngine,
    effect_registry: PackRegistry | None = None,
    rule_registry: PackRegistry | None = None,
    scene_registry: SceneRegistry | None = None,
    effect_admin: EffectAdmin | None = None,
) -> SceneManager:
    """Construct a SceneManager, defaulting any unspecified registry/effect_admin.

    Absorbs SceneManager's injected-EffectAdmin constructor parameter so most
    call sites only need to override the registries/effect_admin they actually
    care about.
    """
    return SceneManager(
        engine,
        effect_registry if effect_registry is not None else PackRegistry(item_attr="BUILD"),
        rule_registry if rule_registry is not None else PackRegistry(item_attr="RULE"),
        scene_registry if scene_registry is not None else SceneRegistry(),
        effect_admin if effect_admin is not None else SpyEffectAdmin(),
    )


class _TestPackRegistry(PackRegistry):
    """PackRegistry subclass that supports registering pre-built instances for testing."""

    def register_instance(
        self, pack_name: str, item_name: str, instance: object, version: str = "1.0"
    ) -> None:
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


def _scene_factory(**kwargs):
    """Return a zero-arg factory producing a Scene from keyword overrides."""

    def factory():
        return Scene(
            effect_packs=kwargs.get("effect_packs", []),
            rule_packs=kwargs.get("rule_packs", []),
            initial_data=kwargs.get("initial_data"),
        )

    return factory


def _scene_registry(*entries) -> SceneRegistry:
    """Return a SceneRegistry pre-loaded with (name, factory) pairs."""
    registry = SceneRegistry()
    for name, factory in entries:
        registry.register(name, factory)
    return registry


def _rule(name: str = "test.rule") -> GameRule:
    return GameRule()


# ---------------------------------------------------------------------------
# SceneControls — abstract base
# ---------------------------------------------------------------------------


def test_scene_controls_load_raises_not_implemented_error() -> None:
    sc = SceneControls()

    with pytest.raises(NotImplementedError):
        sc.load("any")


def test_scene_controls_overlay_raises_not_implemented_error() -> None:
    sc = SceneControls()

    with pytest.raises(NotImplementedError):
        sc.overlay("any")


def test_scene_controls_pop_raises_not_implemented_error() -> None:
    sc = SceneControls()

    with pytest.raises(NotImplementedError):
        sc.pop()


# ---------------------------------------------------------------------------
# Scene — declarative data bundle
# ---------------------------------------------------------------------------


def test_scene_effect_packs_accessible_after_construction() -> None:
    effect_packs = [("fx", "1.0")]
    scene = Scene(effect_packs=effect_packs, rule_packs=[])

    assert scene.effect_packs is effect_packs


def test_scene_rule_packs_accessible_after_construction() -> None:
    rule_packs = [("rules", "2.0")]
    scene = Scene(effect_packs=[], rule_packs=rule_packs)

    assert scene.rule_packs is rule_packs


def test_scene_initial_data_defaults_to_none() -> None:
    scene = Scene(effect_packs=[], rule_packs=[])

    assert scene.initial_data is None


def test_scene_initial_data_accessible_when_provided() -> None:
    data = {"score": 0}
    scene = Scene(effect_packs=[], rule_packs=[], initial_data=data)

    assert scene.initial_data is data


def test_scene_rejects_unknown_attributes() -> None:
    scene = Scene(effect_packs=[], rule_packs=[])

    with pytest.raises(AttributeError):
        scene.runtime_state = "mutable"  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# SceneManager — construction
# ---------------------------------------------------------------------------


def test_scene_manager_satisfies_scene_controls_interface() -> None:
    engine = _make_engine()
    effect_registry = PackRegistry(item_attr="BUILD")
    rule_registry = PackRegistry(item_attr="RULE")
    scene_registry = SceneRegistry()

    manager = _make_scene_manager(
        engine,
        effect_registry=effect_registry,
        rule_registry=rule_registry,
        scene_registry=scene_registry,
    )

    assert isinstance(manager, SceneControls)


def test_load_succeeds_when_scene_is_in_registry() -> None:
    engine = _make_engine()
    scene_reg = _scene_registry(("main", _scene_factory()))
    manager = _make_scene_manager(engine, scene_registry=scene_reg)

    manager.load("main")
    manager.update()  # should not raise


# ---------------------------------------------------------------------------
# SceneManager — active_state
# ---------------------------------------------------------------------------


def test_active_state_is_none_before_any_scene_is_loaded() -> None:
    manager = _make_scene_manager(_make_engine())

    assert manager.active_state is None


def test_active_state_returns_game_state_after_scene_loads() -> None:
    scene_reg = _scene_registry(("main", _scene_factory()))
    manager = _make_scene_manager(_make_engine(), scene_registry=scene_reg)
    manager.load("main")
    manager.update()

    assert isinstance(manager.active_state, GameState)


def test_active_state_is_none_while_load_is_pending_but_not_yet_applied() -> None:
    scene_reg = _scene_registry(("main", _scene_factory()))
    manager = _make_scene_manager(_make_engine(), scene_registry=scene_reg)
    manager.load("main")

    # Transition is recorded but update() has not been called yet
    assert manager.active_state is None


def test_active_state_changes_after_load_replaces_scene() -> None:
    scene_reg = _scene_registry(("first", _scene_factory()), ("second", _scene_factory()))
    manager = _make_scene_manager(_make_engine(), scene_registry=scene_reg)

    manager.load("first")
    manager.update()
    first_state = manager.active_state

    manager.load("second")
    manager.update()

    assert manager.active_state is not first_state


# ---------------------------------------------------------------------------
# SceneManager — immediate validation (ValueError raised before any state change)
# ---------------------------------------------------------------------------


def test_load_raises_immediately_for_unregistered_scene_name() -> None:
    engine = _make_engine()
    manager = _make_scene_manager(engine)

    with pytest.raises(ValueError, match="Unknown scene"):
        manager.load("nonexistent")


def test_overlay_raises_immediately_for_unregistered_scene_name() -> None:
    engine = _make_engine()
    scene_reg = _scene_registry(("base", _scene_factory()))
    manager = _make_scene_manager(engine, scene_registry=scene_reg)
    manager.load("base")
    manager.update()

    with pytest.raises(ValueError, match="Unknown scene"):
        manager.overlay("nonexistent")


def test_overlay_raises_immediately_when_stack_is_empty() -> None:
    engine = _make_engine()
    scene_reg = _scene_registry(("overlay_scene", _scene_factory()))
    manager = _make_scene_manager(engine, scene_registry=scene_reg)

    with pytest.raises(ValueError):
        manager.overlay("overlay_scene")


def test_pop_raises_immediately_with_zero_entries_on_stack() -> None:
    engine = _make_engine()
    manager = _make_scene_manager(engine)

    with pytest.raises(ValueError):
        manager.pop()


def test_pop_raises_immediately_with_exactly_one_entry_on_stack() -> None:
    engine = _make_engine()
    scene_reg = _scene_registry(("main", _scene_factory()))
    manager = _make_scene_manager(engine, scene_registry=scene_reg)
    manager.load("main")
    manager.update()  # apply the load

    with pytest.raises(ValueError):
        manager.pop()


# ---------------------------------------------------------------------------
# SceneManager — pack version validation on load()
# ---------------------------------------------------------------------------


def test_load_raises_for_incompatible_effect_pack_version(pack_env) -> None:
    _make_effect_pack(pack_env, "fx", "1.0")
    effect_registry, rule_registry = _make_registries(str(pack_env))
    engine = _make_engine()
    scene_reg = _scene_registry(
        ("main", _scene_factory(effect_packs=[("fx", "99.0")]))  # incompatible major version
    )
    manager = _make_scene_manager(
        engine,
        effect_registry=effect_registry,
        rule_registry=rule_registry,
        scene_registry=scene_reg,
    )

    with pytest.raises(ValueError):
        manager.load("main")


def test_load_leaves_stack_untouched_when_pack_version_is_incompatible(pack_env) -> None:
    _make_effect_pack(pack_env, "fx", "1.0")
    effect_registry, rule_registry = _make_registries(str(pack_env))
    engine = _make_engine()
    scene_reg = _scene_registry(
        ("initial", _scene_factory()),
        ("bad", _scene_factory(effect_packs=[("fx", "99.0")])),
    )
    manager = _make_scene_manager(
        engine,
        effect_registry=effect_registry,
        rule_registry=rule_registry,
        scene_registry=scene_reg,
    )

    # Load a valid initial scene first
    manager.load("initial")
    manager.update()

    # Attempt to load a scene with incompatible effect pack
    with pytest.raises(ValueError):
        manager.load("bad")

    # Manager should still be usable; loading initial again works
    manager.load("initial")
    manager.update()  # no error


def test_load_raises_for_incompatible_rule_pack_version(pack_env) -> None:
    _make_rule_pack(
        pack_env,
        "rules",
        "1.0",
        {"rule_a": ("from engine.engine import GameRule\nRULE = GameRule()\n")},
    )
    effect_registry, rule_registry = _make_registries(str(pack_env))
    engine = _make_engine()
    scene_reg = _scene_registry(
        ("main", _scene_factory(rule_packs=[("rules", "99.0")]))  # incompatible major version
    )
    manager = _make_scene_manager(
        engine,
        effect_registry=effect_registry,
        rule_registry=rule_registry,
        scene_registry=scene_reg,
    )

    with pytest.raises(ValueError):
        manager.load("main")


# ---------------------------------------------------------------------------
# SceneManager — pack version validation on overlay()
# ---------------------------------------------------------------------------


def test_overlay_validates_packs_before_suspending_active_scene(pack_env) -> None:
    _make_effect_pack(pack_env, "fx", "1.0")
    effect_registry, rule_registry = _make_registries(str(pack_env))
    engine, controls = _make_engine_with_controls()
    scene_reg = _scene_registry(
        ("main", _scene_factory()),
        ("overlay_scene", _scene_factory(effect_packs=[("fx", "99.0")])),
    )
    manager = _make_scene_manager(
        engine,
        effect_registry=effect_registry,
        rule_registry=rule_registry,
        scene_registry=scene_reg,
    )

    manager.load("main")
    manager.update()
    controls.stopped_scopes.clear()

    with pytest.raises(ValueError):
        manager.overlay("overlay_scene")

    assert controls.stopped_scopes == [], (
        "effects must not be stopped when overlay pack validation fails"
    )


# ---------------------------------------------------------------------------
# SceneManager — update() engine delegation and deferred transitions
# ---------------------------------------------------------------------------


def test_update_skips_engine_update_when_stack_is_empty() -> None:
    engine = _make_engine()
    manager = _make_scene_manager(engine)

    # No exception should be raised; engine.update would fail without a state
    manager.update()


def test_update_calls_engine_update_with_active_state_on_each_tick() -> None:
    engine = _TrackingEngine(_RecordingEffectControls())
    scene_reg = _scene_registry(("main", _scene_factory()))
    manager = _make_scene_manager(engine, scene_registry=scene_reg)
    manager.load("main")
    manager.update()  # stack empty at start of tick; engine.update skipped; load fires

    assert engine._update_calls == [], "engine.update must be skipped when stack is empty"

    manager.update()  # stack now has one entry; engine.update fires
    assert len(engine._update_calls) == 1

    manager.update()  # another tick; same active state passed each time
    assert len(engine._update_calls) == 2
    assert engine._update_calls[0] is engine._update_calls[1]


class _TrackingEngine(GameEngine):
    """GameEngine subclass that records each update() call for order verification."""

    def __init__(self, effect_controls: EffectControls) -> None:
        super().__init__(effect_controls=effect_controls)
        self._update_calls: list = []

    @property
    def _last_state(self) -> GameState:
        return self._update_calls[-1]

    def update(self, state: GameState) -> None:
        self._update_calls.append(state)
        super().update(state)


def test_transition_applies_after_engine_update_in_same_tick() -> None:
    engine = _TrackingEngine(_RecordingEffectControls())
    scene_reg = _scene_registry(("main", _scene_factory()))
    manager = _make_scene_manager(engine, scene_registry=scene_reg)

    manager.load("main")
    manager.update()

    # First update: stack was empty so engine.update skipped; load applies
    assert engine._update_calls == [], "engine.update must be skipped when stack is empty"
    assert manager.active_state is not None, "load must apply within this tick"

    # Second update: stack has one entry, engine.update fires; then pending load executes
    engine._update_calls.clear()
    manager.load("main")
    manager.update()

    assert len(engine._update_calls) == 1, "engine.update must run before the transition"
    assert manager.active_state is not None


def test_last_pending_transition_wins_within_one_tick() -> None:
    engine = _make_engine()
    scene_reg = _scene_registry(
        ("scene_a", _scene_factory(initial_data={"which": "a"})),
        ("scene_b", _scene_factory(initial_data={"which": "b"})),
    )
    manager = _make_scene_manager(engine, scene_registry=scene_reg)

    # Both recorded in one tick — last wins
    manager.load("scene_a")
    manager.load("scene_b")
    manager.update()
    manager.update()  # engine.update(active_state)

    assert manager.active_state.get_or_none("which", str) == "b", (
        "last load() call in tick should win"
    )


def test_overlay_wins_when_load_and_overlay_both_called_in_same_tick() -> None:
    engine = _make_engine()
    scene_reg = _scene_registry(
        ("base", _scene_factory(initial_data={"which": "base"})),
        ("new", _scene_factory()),
        ("overlay_scene", _scene_factory(initial_data={"which": "overlay"})),
    )
    manager = _make_scene_manager(engine, scene_registry=scene_reg)

    manager.load("base")
    manager.update()
    manager.update()  # tick on base

    # In the same tick: load first, then overlay — overlay (last call) wins.
    # overlay suspends base rather than unloading it; load would have replaced it.
    manager.load("new")
    manager.overlay("overlay_scene")
    manager.update()
    manager.update()  # tick on overlay

    # overlay was applied: the overlay scene is on top of base
    assert manager.active_state.get_or_none("which", str) == "overlay"
    # popping returns to the suspended base, proving overlay suspended (not replaced) it
    manager.pop()
    manager.update()
    manager.update()
    assert manager.active_state.get_or_none("which", str) == "base"


# ---------------------------------------------------------------------------
# SceneManager — load() lifecycle
# ---------------------------------------------------------------------------


def test_load_passes_scene_manager_as_scene_controls_in_active_state() -> None:
    engine = _TrackingEngine(_RecordingEffectControls())
    scene_reg = _scene_registry(("main", _scene_factory()))
    manager = _make_scene_manager(engine, scene_registry=scene_reg)
    manager.load("main")
    manager.update()  # load fires; state created
    manager.update()  # engine.update(active_state)

    assert engine._last_state.scene_controls is manager


def test_load_seeds_active_state_data_from_scene_initial_data() -> None:
    engine = _TrackingEngine(_RecordingEffectControls())
    scene_reg = _scene_registry(("main", _scene_factory(initial_data={"level": 5})))
    manager = _make_scene_manager(engine, scene_registry=scene_reg)
    manager.load("main")
    manager.update()  # load fires; state created with initial_data
    manager.update()  # engine.update(active_state); _last_state is now set

    assert engine._last_state.get_or_none("level", int) == 5


def test_load_stops_all_effects_on_the_outgoing_scene() -> None:
    engine, controls = _make_engine_with_controls()
    scene_reg = _scene_registry(("main", _scene_factory()), ("next", _scene_factory()))
    manager = _make_scene_manager(engine, scene_registry=scene_reg)
    manager.load("main")
    manager.update()
    controls.stopped_scopes.clear()

    manager.load("next")
    manager.update()

    assert controls.stopped_scopes == [Scope.ALL]


def test_first_load_does_not_stop_effects_with_empty_stack() -> None:
    engine, controls = _make_engine_with_controls()
    scene_reg = _scene_registry(("main", _scene_factory()))
    manager = _make_scene_manager(engine, scene_registry=scene_reg)
    manager.load("main")
    manager.update()

    assert controls.stopped_scopes == [], "no outgoing scene means nothing to stop"


def test_load_stops_effects_on_every_stack_entry() -> None:
    engine, controls = _make_engine_with_controls()
    scene_reg = _scene_registry(
        ("base", _scene_factory()),
        ("top", _scene_factory()),
        ("new", _scene_factory()),
    )
    manager = _make_scene_manager(engine, scene_registry=scene_reg)

    # Load base, then overlay top so stack has two entries
    manager.load("base")
    manager.update()
    manager.overlay("top")
    manager.update()
    controls.stopped_scopes.clear()

    # Now load "new" — should stop effects on both outgoing entries
    manager.load("new")
    manager.update()

    assert controls.stopped_scopes == [Scope.ALL, Scope.ALL]


def test_overlay_stops_all_effects_on_the_suspended_scene() -> None:
    engine, controls = _make_engine_with_controls()
    scene_reg = _scene_registry(("main", _scene_factory()), ("overlay_scene", _scene_factory()))
    manager = _make_scene_manager(engine, scene_registry=scene_reg)
    manager.load("main")
    manager.update()
    controls.stopped_scopes.clear()

    manager.overlay("overlay_scene")
    manager.update()

    assert controls.stopped_scopes == [Scope.ALL]


def test_pop_stops_all_effects_on_the_popped_scene() -> None:
    engine, controls = _make_engine_with_controls()
    scene_reg = _scene_registry(("main", _scene_factory()), ("overlay_scene", _scene_factory()))
    manager = _make_scene_manager(engine, scene_registry=scene_reg)
    manager.load("main")
    manager.update()
    manager.overlay("overlay_scene")
    manager.update()
    controls.stopped_scopes.clear()

    manager.pop()
    manager.update()

    assert controls.stopped_scopes == [Scope.ALL]


def test_load_clears_suspended_state_queues_so_stale_events_do_not_outlive_the_stack() -> None:
    engine = _TrackingEngine(_RecordingEffectControls())
    rule_registry = _TestPackRegistry(item_attr="RULE")
    base_events = []

    class _BaseRule(GameRule):
        def handle_event(self, event: Event, state: GameState) -> None:
            base_events.append(event.name)

    base_rule = _BaseRule()
    rule_registry.register_instance("stubs", "base_rule", base_rule)
    scene_reg = _scene_registry(
        ("base", _scene_factory(rule_packs=[("stubs", "1.0")])),
        ("overlay_scene", _scene_factory()),
        ("new", _scene_factory()),
    )
    manager = _make_scene_manager(engine, rule_registry=rule_registry, scene_registry=scene_reg)

    # Build a 2-layer stack
    manager.load("base")
    manager.update()
    manager.update()  # tick; engine._last_state = base_state
    base_state = engine._last_state

    manager.overlay("overlay_scene")
    manager.update()  # overlay fires; base_state.clear_queue() called

    # Queue a stale event on the now-suspended base_state
    base_state.queue_event(Event(_GROUP, "stale"))

    # load("new") clears queues on all outgoing states (including suspended base_state)
    manager.load("new")
    manager.update()  # engine.update(overlay_state), then _do_load clears base_state

    # "stale" was on base_state, which is now discarded; base_rule is no longer in engine
    # and base_state is gone. Verify no base events beyond the clear.
    assert "stale" not in base_events


def test_load_dispatches_events_to_scene_rules_on_following_ticks(pack_env) -> None:
    _make_rule_pack(
        pack_env,
        "rules",
        "1.0",
        {"rule_a": ("from engine.engine import GameRule\nRULE = GameRule()\n")},
    )
    effect_registry, rule_registry = _make_registries(str(pack_env))
    engine = _TrackingEngine(_RecordingEffectControls())

    fired: list = []

    class _SceneRule(GameRule):
        def handle_event(self, event: Event, state: GameState) -> None:
            fired.append("scene")

    pack_rule = rule_registry.get("rules", "rule_a", GameRule)
    pack_rule.on(Event, lambda e, s: fired.append("pack"))

    scene_r = _SceneRule()
    rule_registry.register_instance("stubs", "scene_rule", scene_r)
    scene_reg = _scene_registry(
        ("main", _scene_factory(rule_packs=[("stubs", "1.0"), ("rules", "1.0")]))
    )
    manager = _make_scene_manager(
        engine,
        effect_registry=effect_registry,
        rule_registry=rule_registry,
        scene_registry=scene_reg,
    )
    manager.load("main")
    manager.update()  # load fires; state created
    manager.update()  # engine.update(active_state)

    engine._last_state.queue_event(Event(_GROUP, "verify"))
    manager.update()

    assert "scene" in fired, "scene rule must receive events after load"
    assert "pack" in fired, "pack rule must receive events after load"


def test_scene_rules_fire_before_pack_rules(pack_env) -> None:
    _make_rule_pack(
        pack_env,
        "rules",
        "1.0",
        {"rule_a": ("from engine.engine import GameRule\nRULE = GameRule()\n")},
    )
    effect_registry, rule_registry = _make_registries(str(pack_env))
    engine = _TrackingEngine(_RecordingEffectControls())

    fired: list = []

    class _SceneRule(GameRule):
        def handle_event(self, event: Event, state: GameState) -> None:
            fired.append("scene")

    pack_rule = rule_registry.get("rules", "rule_a", GameRule)
    pack_rule.on(Event, lambda e, s: fired.append("pack"))

    scene_r = _SceneRule()
    rule_registry.register_instance("stubs", "scene_rule", scene_r)
    scene_reg = _scene_registry(
        ("main", _scene_factory(rule_packs=[("stubs", "1.0"), ("rules", "1.0")]))
    )
    manager = _make_scene_manager(
        engine,
        effect_registry=effect_registry,
        rule_registry=rule_registry,
        scene_registry=scene_reg,
    )
    manager.load("main")
    manager.update()
    manager.update()

    engine._last_state.queue_event(Event(_GROUP, "verify"))
    manager.update()

    assert fired.index("scene") < fired.index("pack")


# ---------------------------------------------------------------------------
# SceneManager — overlay() lifecycle
# ---------------------------------------------------------------------------


def test_overlay_suspends_active_scene_and_pushes_without_clearing_stack() -> None:
    engine = _make_engine()
    scene_reg = _scene_registry(
        ("base", _scene_factory(initial_data={"which": "base"})),
        ("overlay_scene", _scene_factory(initial_data={"which": "overlay"})),
    )
    manager = _make_scene_manager(engine, scene_registry=scene_reg)

    manager.load("base")
    manager.update()
    manager.update()  # tick on base

    manager.overlay("overlay_scene")
    manager.update()
    manager.update()  # tick on overlay
    assert manager.active_state.get_or_none("which", str) == "overlay"

    # base was suspended (not cleared): popping restores it
    manager.pop()
    manager.update()
    manager.update()
    assert manager.active_state.get_or_none("which", str) == "base"


def test_overlay_clears_suspended_base_state_queue_before_pushing() -> None:
    engine = _TrackingEngine(_RecordingEffectControls())
    rule_registry = _TestPackRegistry(item_attr="RULE")
    base_events = []

    class _BaseRule(GameRule):
        def handle_event(self, event: Event, state: GameState) -> None:
            base_events.append(event.name)

    base_rule = _BaseRule()
    rule_registry.register_instance("stubs", "base_rule", base_rule)
    scene_reg = _scene_registry(
        ("base", _scene_factory(rule_packs=[("stubs", "1.0")])),
        ("overlay_scene", _scene_factory()),
    )
    manager = _make_scene_manager(engine, rule_registry=rule_registry, scene_registry=scene_reg)

    manager.load("base")
    manager.update()
    manager.update()  # engine.update(base_state)
    base_state = engine._last_state

    # Queue a stale event, then overlay (which clears the base_state queue)
    base_state.queue_event(Event(_GROUP, "stale"))
    manager.overlay("overlay_scene")
    manager.update()  # engine.update on base, then overlay fires + clears base_state queue

    # After overlay, queue another event on the suspended base_state externally
    base_state.queue_event(Event(_GROUP, "while_suspended"))
    manager.pop()
    manager.update()  # pop fires: defensive clear_queue on base_state, then on_resume
    manager.update()  # engine.update(base_state); "while_suspended" must have been cleared

    assert "while_suspended" not in base_events, (
        "event queued while suspended must not replay after pop"
    )


# ---------------------------------------------------------------------------
# SceneManager — pop() lifecycle
# ---------------------------------------------------------------------------


def test_pop_restores_base_scene_rules_so_events_dispatch_to_base_rules(pack_env) -> None:
    _make_rule_pack(
        pack_env,
        "rules",
        "1.0",
        {"rule_a": ("from engine.engine import GameRule\nRULE = GameRule()\n")},
    )
    effect_registry, rule_registry = _make_registries(str(pack_env))
    engine = _TrackingEngine(_RecordingEffectControls())

    base_events: list = []

    class _BaseRule(GameRule):
        def handle_event(self, event: Event, state: GameState) -> None:
            base_events.append(event.name)

    base_rule = _BaseRule()
    rule_registry.register_instance("stubs", "base_rule", base_rule)
    pack_rule = rule_registry.get("rules", "rule_a", GameRule)
    pack_events: list = []
    pack_rule.on(Event, lambda e, s: pack_events.append(e.name))

    scene_reg = _scene_registry(
        ("base", _scene_factory(rule_packs=[("stubs", "1.0"), ("rules", "1.0")])),
        ("overlay_scene", _scene_factory()),
    )
    manager = _make_scene_manager(
        engine,
        effect_registry=effect_registry,
        rule_registry=rule_registry,
        scene_registry=scene_reg,
    )

    manager.load("base")
    manager.update()  # load fires; stack empty at start so engine.update skipped
    manager.update()  # tick on base; _last_state = base_state
    manager.overlay("overlay_scene")
    manager.update()  # engine.update(base_state), then overlay fires
    manager.pop()
    manager.update()  # engine.update(overlay_state), then pop fires; base rules restored
    manager.update()  # engine.update(base_state); _last_state = base_state

    engine._last_state.queue_event(Event(_GROUP, "verify"))
    manager.update()

    assert "verify" in base_events, "base_rule must receive events after pop restores base scene"
    assert "verify" in pack_events, "pack_rule must receive events after pop restores base scene"


def test_pop_clears_restored_state_queue_so_suspended_events_do_not_replay() -> None:
    engine = _TrackingEngine(_RecordingEffectControls())
    rule_registry = _TestPackRegistry(item_attr="RULE")
    base_events: list = []

    class _BaseRule(GameRule):
        def handle_event(self, event: Event, state: GameState) -> None:
            base_events.append(event.name)

    base_rule = _BaseRule()
    rule_registry.register_instance("stubs", "base_rule", base_rule)
    scene_reg = _scene_registry(
        ("base", _scene_factory(rule_packs=[("stubs", "1.0")])),
        ("overlay_scene", _scene_factory()),
    )
    manager = _make_scene_manager(engine, rule_registry=rule_registry, scene_registry=scene_reg)

    manager.load("base")
    manager.update()
    manager.update()  # engine.update(base_state); _last_state = base_state
    base_state = engine._last_state

    manager.overlay("overlay_scene")
    manager.update()  # overlay fires; base_state.clear_queue() called

    # Directly queue a stale event on the suspended base_state
    base_state.queue_event(Event(_GROUP, "stale_while_suspended"))

    manager.pop()
    manager.update()  # pop fires: defensive clear_queue on base_state before on_resume
    manager.update()  # engine.update(base_state) — stale event must not fire

    assert "stale_while_suspended" not in base_events, (
        "events queued on suspended state must be discarded by pop's defensive clear_queue"
    )


def test_pop_restores_scene_below_in_deep_overlay_stack() -> None:
    engine = _make_engine()
    scene_reg = _scene_registry(
        ("base", _scene_factory(initial_data={"which": "base"})),
        ("mid", _scene_factory(initial_data={"which": "mid"})),
        ("top", _scene_factory(initial_data={"which": "top"})),
    )
    manager = _make_scene_manager(engine, scene_registry=scene_reg)

    manager.load("base")
    manager.update()
    manager.overlay("mid")
    manager.update()
    manager.overlay("top")
    manager.update()
    manager.update()  # tick on top

    manager.pop()
    manager.update()
    manager.update()  # tick on restored scene

    assert manager.active_state.get_or_none("which", str) == "mid", (
        "pop from 3-layer stack must restore the scene directly below"
    )

    manager.pop()
    manager.update()
    manager.update()

    assert manager.active_state.get_or_none("which", str) == "base"


# ---------------------------------------------------------------------------
# SceneManager — rule pack integration
# ---------------------------------------------------------------------------


def test_rule_pack_items_all_receive_events_after_load(pack_env) -> None:
    rule_content = "from engine.engine import GameRule\nRULE = GameRule()\n"
    _make_rule_pack(
        pack_env,
        "rules",
        "1.0",
        {
            "rule_a": rule_content,
            "rule_b": rule_content,
        },
    )
    effect_registry, rule_registry = _make_registries(str(pack_env))
    engine = _TrackingEngine(_RecordingEffectControls())

    fired_by: list = []

    class _SceneRule(GameRule):
        def handle_event(self, event: Event, state: GameState) -> None:
            fired_by.append("scene")

    pack_rule_a = rule_registry.get("rules", "rule_a", GameRule)
    pack_rule_b = rule_registry.get("rules", "rule_b", GameRule)
    pack_rule_a.on(Event, lambda e, s: fired_by.append("pack_a"))
    pack_rule_b.on(Event, lambda e, s: fired_by.append("pack_b"))

    scene_r = _SceneRule()
    rule_registry.register_instance("stubs", "scene_rule", scene_r)
    scene_reg = _scene_registry(
        ("main", _scene_factory(rule_packs=[("stubs", "1.0"), ("rules", "1.0")]))
    )
    manager = _make_scene_manager(
        engine,
        effect_registry=effect_registry,
        rule_registry=rule_registry,
        scene_registry=scene_reg,
    )
    manager.load("main")
    manager.update()  # load fires
    manager.update()  # engine.update(active_state)

    engine._last_state.queue_event(Event(_GROUP, "verify"))
    manager.update()

    assert "scene" in fired_by, "scene rule must fire"
    assert "pack_a" in fired_by, "pack rule_a must fire"
    assert "pack_b" in fired_by, "pack rule_b must fire"


def test_rule_pack_items_loaded_in_alphabetical_order(pack_env) -> None:
    rule_template = (
        "from engine.engine import GameRule\nimport engine.scene as _s\nRULE = GameRule()\n"
    )
    _make_rule_pack(
        pack_env,
        "rules",
        "1.0",
        {
            "z_rule": rule_template,
            "a_rule": rule_template,
            "m_rule": rule_template,
        },
    )
    _effect_registry, rule_registry = _make_registries(str(pack_env))

    # Verify items() returns alphabetical order
    items = rule_registry.items("rules")
    assert items == sorted(items)


# ---------------------------------------------------------------------------
# SceneManager — GC eligibility after full unload
# ---------------------------------------------------------------------------


def test_unloaded_scene_is_not_retained_by_manager() -> None:
    import gc
    import weakref

    engine = _make_engine()
    created_scene = None

    def factory():
        nonlocal created_scene
        created_scene = Scene(effect_packs=[], rule_packs=[])
        return created_scene

    scene_reg = _scene_registry(("main", factory), ("other", _scene_factory()))
    manager = _make_scene_manager(engine, scene_registry=scene_reg)

    manager.load("main")
    manager.update()

    ref = weakref.ref(created_scene)
    created_scene = None  # drop local reference

    # Now load a different scene to trigger unload of "main"
    manager.load("other")
    manager.update()

    gc.collect()
    assert ref() is None, "Scene should be GC-eligible after full unload"


# ---------------------------------------------------------------------------
# SceneManager — activation invariant pin
# ---------------------------------------------------------------------------


def test_pop_activates_revealed_entry_with_both_rules_and_local_effects() -> None:
    """After load → overlay → pop, the revealed entry has rules on the engine
    AND its local effect registry pushed to the effect controls (invariant: no half-activation)."""
    engine = _make_engine()
    base_local_registry = Scene(effect_packs=[], rule_packs=[]).local_effect_registry
    base_rule = GameRule()
    rule_registry = _TestPackRegistry(item_attr="RULE")
    rule_registry.register_instance("stubs", "base_rule", base_rule)

    base_events: list = []
    base_rule.on(Event, lambda e, s: base_events.append(e.name))

    def base_factory():
        return Scene(
            effect_packs=[],
            rule_packs=[("stubs", "1.0")],
            local_effect_registry=base_local_registry,
        )

    scene_reg = SceneRegistry()
    scene_reg.register("base", base_factory)
    scene_reg.register("overlay_scene", _scene_factory())
    effect_admin = SpyEffectAdmin()
    manager = _make_scene_manager(
        engine, rule_registry=rule_registry, scene_registry=scene_reg, effect_admin=effect_admin
    )

    manager.load("base")
    manager.update()
    manager.overlay("overlay_scene")
    manager.update()
    effect_admin.local_effects_history.clear()

    manager.pop()
    manager.update()

    manager.active_state.queue_event(Event(_GROUP, "check"))
    manager.update()
    assert base_events, "base rules must be active on the engine after pop"
    assert effect_admin.local_effects_history, (
        "set_local_effects must be called when pop reveals the base entry"
    )
    assert effect_admin.local_effects_history[-1] is base_local_registry, (
        "pop must push the revealed entry's own local_effect_registry"
    )


# ---------------------------------------------------------------------------
# SceneManager — resolution-failure ordering
# ---------------------------------------------------------------------------


def test_load_whose_rule_resolution_fails_does_not_stop_effects_on_active_scene() -> None:
    """Rule resolution runs before teardown; a failure must leave the active scene untouched."""
    engine, controls = _make_engine_with_controls()
    rule_registry = _TestPackRegistry(item_attr="RULE")
    existing_rule = GameRule()
    rule_registry.register_instance("stubs", "existing_rule", existing_rule)

    class _BrokenRegistry:
        def items(self):
            raise ValueError("simulated rule load failure")

    def bad_factory():
        scene = Scene(effect_packs=[], rule_packs=[])
        object.__setattr__(scene, "local_rule_registry", _BrokenRegistry())
        return scene

    scene_reg = SceneRegistry()
    scene_reg.register("initial", _scene_factory(rule_packs=[("stubs", "1.0")]))
    scene_reg.register("bad", bad_factory)
    manager = _make_scene_manager(engine, rule_registry=rule_registry, scene_registry=scene_reg)

    manager.load("initial")
    manager.update()
    controls.stopped_scopes.clear()

    manager.load("bad")
    with pytest.raises(ValueError, match="simulated rule load failure"):
        manager.update()

    assert controls.stopped_scopes == [], (
        "effects must not be stopped when rule resolution fails during load"
    )


def test_suspended_scene_remains_on_stack_after_overlay() -> None:
    import gc
    import weakref

    engine = _make_engine()
    created_scene = None

    def factory():
        nonlocal created_scene
        created_scene = Scene(effect_packs=[], rule_packs=[])
        return created_scene

    scene_reg = _scene_registry(("base", factory), ("overlay_scene", _scene_factory()))
    manager = _make_scene_manager(engine, scene_registry=scene_reg)

    manager.load("base")
    manager.update()

    ref = weakref.ref(created_scene)
    created_scene = None

    manager.overlay("overlay_scene")
    manager.update()

    gc.collect()
    assert ref() is not None, "Suspended scene should remain on stack (not GC'd)"


# ---------------------------------------------------------------------------
# SceneManager — merge-strategy scene lifecycle (issue #587)
# ---------------------------------------------------------------------------


def _make_merge_strategy_scene_manager(pack_env, scene_names):
    """Return (scene_manager, effect_manager, output).

    Wires a real ``EffectManager`` (not the recording stub) as the engine's
    effect controls, with a 'color' pack providing solid-fill 'red'/'blue'
    effects, so merge-strategy behaviour can be observed on composed pixels.
    """
    _make_color_effect_pack(pack_env, "color")
    effect_registry = PackRegistry(item_attr="BUILD")
    effect_registry.scan_dir(str(pack_env), MODULE_PREFIX)
    output = SpyEffectOutput(min_resolution=10, scopes=[Scope.PERSONAL])
    effect_manager = EffectManager(registry=effect_registry, outputs=[output])
    engine = GameEngine(effect_controls=effect_manager)
    scene_reg = _scene_registry(*[(name, _scene_factory()) for name in scene_names])
    scene_manager = _make_scene_manager(
        engine,
        effect_registry=effect_registry,
        scene_registry=scene_reg,
        effect_admin=effect_manager,
    )
    return scene_manager, effect_manager, output


def _fill_personal_and_tick(effect_manager, output) -> list:
    """Add fresh red+blue effects to PERSONAL, tick once, and return the composed pixels."""
    effect_manager.add_effect(Scope.PERSONAL, "color.red", {})
    effect_manager.add_effect(Scope.PERSONAL, "color.blue", {})
    effect_manager.update(Timer())
    _, composed = output.update_pixels_calls[-1]
    return list(composed)


_SPLIT_RED_BLUE = [0xFF0000] * 5 + [0x0000FF] * 5
_ADDITIVE_RED_BLUE = [0xFF00FF] * 10


def test_scene_load_resets_merge_strategy_to_split(pack_env) -> None:
    scene_manager, effect_manager, output = _make_merge_strategy_scene_manager(
        pack_env, ["base", "next"]
    )
    scene_manager.load("base")
    scene_manager.update()
    effect_manager.set_merge_strategy(Scope.PERSONAL, ADDITIVE)
    assert _fill_personal_and_tick(effect_manager, output) == _ADDITIVE_RED_BLUE

    scene_manager.load("next")
    scene_manager.update()

    assert _fill_personal_and_tick(effect_manager, output) == _SPLIT_RED_BLUE, (
        "load must reset every scope key back to Split"
    )


def test_scene_overlay_inherits_the_underlying_scenes_live_merge_strategy(pack_env) -> None:
    scene_manager, effect_manager, output = _make_merge_strategy_scene_manager(
        pack_env, ["base", "overlay_scene"]
    )
    scene_manager.load("base")
    scene_manager.update()
    effect_manager.set_merge_strategy(Scope.PERSONAL, ADDITIVE)

    scene_manager.overlay("overlay_scene")
    scene_manager.update()

    assert _fill_personal_and_tick(effect_manager, output) == _ADDITIVE_RED_BLUE, (
        "overlay must start seeing exactly the underlying scene's current choice"
    )


def test_scene_overlay_merge_strategy_change_takes_effect_the_next_tick(pack_env) -> None:
    scene_manager, effect_manager, output = _make_merge_strategy_scene_manager(
        pack_env, ["base", "overlay_scene"]
    )
    scene_manager.load("base")
    scene_manager.update()
    scene_manager.overlay("overlay_scene")
    scene_manager.update()
    assert _fill_personal_and_tick(effect_manager, output) == _SPLIT_RED_BLUE

    effect_manager.set_merge_strategy(Scope.PERSONAL, ADDITIVE)
    effect_manager.update(Timer())

    _, composed = output.update_pixels_calls[-1]
    assert list(composed) == _ADDITIVE_RED_BLUE, (
        "a set_merge_strategy call during an overlay must apply from its very next tick"
    )


def test_scene_pop_restores_pre_overlay_merge_strategy_discarding_overlay_changes(
    pack_env,
) -> None:
    scene_manager, effect_manager, output = _make_merge_strategy_scene_manager(
        pack_env, ["base", "overlay_scene"]
    )
    scene_manager.load("base")
    scene_manager.update()  # base starts at the default Split
    scene_manager.overlay("overlay_scene")
    scene_manager.update()
    effect_manager.set_merge_strategy(Scope.PERSONAL, ADDITIVE)  # overlay-only change

    scene_manager.pop()
    scene_manager.update()

    assert _fill_personal_and_tick(effect_manager, output) == _SPLIT_RED_BLUE, (
        "pop must restore base's pre-overlay Split choice, discarding the overlay's Additive"
    )


def test_nested_overlay_pop_merge_strategy_change_never_leaks_past_its_own_pop(
    pack_env,
) -> None:
    scene_manager, effect_manager, output = _make_merge_strategy_scene_manager(
        pack_env, ["base", "mid", "top"]
    )
    scene_manager.load("base")
    scene_manager.update()  # base: Split

    scene_manager.overlay("mid")
    scene_manager.update()
    effect_manager.set_merge_strategy(Scope.PERSONAL, ADDITIVE)  # mid's own choice

    scene_manager.overlay("top")
    scene_manager.update()
    effect_manager.set_merge_strategy(Scope.PERSONAL, SPLIT)  # top-only change

    scene_manager.pop()  # leave top; discard top's change, restore mid's Additive
    scene_manager.update()
    assert _fill_personal_and_tick(effect_manager, output) == _ADDITIVE_RED_BLUE, (
        "mid's Additive choice must survive popping the nested top overlay"
    )

    scene_manager.pop()  # leave mid; discard mid's change, restore base's original Split
    scene_manager.update()
    assert _fill_personal_and_tick(effect_manager, output) == _SPLIT_RED_BLUE, (
        "base's original Split choice must be restored once every overlay above it is popped"
    )
