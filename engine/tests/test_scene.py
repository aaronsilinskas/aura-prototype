"""Tests for engine.scene: Scene, SceneControls, and SceneManager."""

from __future__ import annotations

import pytest

from engine.capabilities import MissingCapabilityError
from engine.effects.merge import ADDITIVE, SPLIT
from engine.engine import GameEngine, GameRule
from engine.events import Event, EventGroup
from engine.packs import PackRegistry
from engine.scene import PackReference, Scene, SceneManager, SceneRegistry
from engine.settings import Settings
from engine.state import EffectControls, GameState, SceneControls, SceneReboot, Scope
from engine.tests.effects.helpers import SpyEffectOutput
from engine.tests.helpers import (
    RecordingSceneReboot,
    SpyEffectAdmin,
    active_state,
    make_scene_runtime,
)
from engine.timer import Timer
from engine.version import Version

# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

_GROUP = EventGroup("test")

_COLOR_EFFECTS = {
    "red": (
        "from engine.tests.effects.helpers import ColorFillEffectBuilder\n"
        "BUILD = ColorFillEffectBuilder(0xFF0000)\n"
    ),
    "blue": (
        "from engine.tests.effects.helpers import ColorFillEffectBuilder\n"
        "BUILD = ColorFillEffectBuilder(0x0000FF)\n"
    ),
}
"""Solid-fill 'red' and 'blue' effect items for merge-strategy tests."""

_GAME_RULE_SOURCE = "from engine.engine import GameRule\nRULE = GameRule()\n"


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
    rule_registry: PackRegistry | None = None,
    scene_registry: SceneRegistry | None = None,
    effect_admin: SpyEffectAdmin | None = None,
    scene_reboot: SceneReboot | None = None,
) -> SceneManager:
    """Construct a SceneManager, defaulting any unspecified registry/admin/port.

    Absorbs SceneManager's injected-EffectAdmin/SceneReboot constructor
    parameters so most call sites only need to override the
    registries/admins/ports they actually care about.
    """
    return SceneManager(
        engine,
        rule_registry if rule_registry is not None else PackRegistry(),
        scene_registry if scene_registry is not None else SceneRegistry(),
        effect_admin if effect_admin is not None else SpyEffectAdmin(),
        scene_reboot if scene_reboot is not None else RecordingSceneReboot(),
    )


def _ref(name: str) -> PackReference:
    """A reference to pack *name* at minimum version 1.0."""
    return PackReference(name, Version(1, 0))


def _scene_factory(**kwargs):
    """Return a zero-arg factory producing a Scene from keyword overrides."""

    def factory():
        return Scene(
            effect_packs=kwargs.get("effect_packs", []),
            rule_packs=kwargs.get("rule_packs", []),
            settings=kwargs.get("settings"),
        )

    return factory


def _which(name: str) -> Settings:
    """Settings telling a scene's state apart: scene Setting ``which`` is *name*."""
    return Settings({"scene": {"which": name}})


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


def test_scene_controls_overlay_raises_not_implemented_error() -> None:
    sc = SceneControls()

    with pytest.raises(NotImplementedError):
        sc.overlay("any")


def test_scene_controls_pop_raises_not_implemented_error() -> None:
    sc = SceneControls()

    with pytest.raises(NotImplementedError):
        sc.pop()


def test_scene_controls_reboot_into_raises_not_implemented_error() -> None:
    sc = SceneControls()

    with pytest.raises(NotImplementedError):
        sc.reboot_into("any")


def test_scene_controls_reboot_to_previous_raises_not_implemented_error() -> None:
    sc = SceneControls()

    with pytest.raises(NotImplementedError):
        sc.reboot_to_previous()


def test_scene_reboot_reboot_into_raises_not_implemented_error() -> None:
    port = SceneReboot()

    with pytest.raises(NotImplementedError):
        port.reboot_into("any")


def test_scene_reboot_reboot_to_previous_raises_not_implemented_error() -> None:
    port = SceneReboot()

    with pytest.raises(NotImplementedError):
        port.reboot_to_previous()


# ---------------------------------------------------------------------------
# Scene — declarative data bundle
# ---------------------------------------------------------------------------


def test_scene_effect_packs_accessible_after_construction() -> None:
    effect_packs = [_ref("fx")]
    scene = Scene(effect_packs=effect_packs, rule_packs=[])

    assert scene.effect_packs is effect_packs


def test_scene_rule_packs_accessible_after_construction() -> None:
    rule_packs = [_ref("rules")]
    scene = Scene(effect_packs=[], rule_packs=rule_packs)

    assert scene.rule_packs is rule_packs


def test_scene_rejects_unknown_attributes() -> None:
    scene = Scene(effect_packs=[], rule_packs=[])

    with pytest.raises(AttributeError):
        scene.runtime_state = "mutable"  # type: ignore[attr-defined]  # slotted, must raise


# ---------------------------------------------------------------------------
# SceneManager — construction
# ---------------------------------------------------------------------------


def test_scene_manager_satisfies_scene_controls_interface() -> None:
    engine = _make_engine()
    rule_registry = PackRegistry()
    scene_registry = SceneRegistry()

    manager = _make_scene_manager(
        engine,
        rule_registry=rule_registry,
        scene_registry=scene_registry,
    )

    assert isinstance(manager, SceneControls)


# ---------------------------------------------------------------------------
# SceneManager — active_state
# ---------------------------------------------------------------------------


def test_active_state_is_none_before_any_scene_is_loaded() -> None:
    manager = _make_scene_manager(_make_engine())

    assert manager.active_state is None


# ---------------------------------------------------------------------------
# SceneManager — immediate validation (ValueError raised before any state change)
# ---------------------------------------------------------------------------


def test_overlay_raises_immediately_for_unregistered_scene_name() -> None:
    engine = _make_engine()
    scene_reg = _scene_registry(("base", _scene_factory()))
    manager = _make_scene_manager(engine, scene_registry=scene_reg)
    manager.activate_boot_scene("base")

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
    manager.activate_boot_scene("main")

    with pytest.raises(ValueError):
        manager.pop()


# ---------------------------------------------------------------------------
# SceneManager — reboot_into / reboot_to_previous (immediate, not deferred)
# ---------------------------------------------------------------------------


def test_reboot_into_delegates_to_the_injected_scene_reboot_port() -> None:
    engine = _make_engine()
    scene_reg = _scene_registry(("tag", _scene_factory()))
    scene_reboot = RecordingSceneReboot()
    manager = _make_scene_manager(engine, scene_registry=scene_reg, scene_reboot=scene_reboot)

    manager.reboot_into("tag")

    assert scene_reboot.reboot_into_calls == ["tag"]


def test_reboot_into_rejects_an_unregistered_scene_name_and_persists_nothing() -> None:
    """An unknown target must never reach the port -- a typo persisted there
    would brick the next boot."""
    engine = _make_engine()
    scene_reboot = RecordingSceneReboot()
    manager = _make_scene_manager(engine, scene_reboot=scene_reboot)

    with pytest.raises(ValueError, match="unknown scene"):
        manager.reboot_into("nonexistent")

    assert scene_reboot.reboot_into_calls == []


def test_reboot_to_previous_delegates_to_the_injected_scene_reboot_port() -> None:
    engine = _make_engine()
    scene_reboot = RecordingSceneReboot()
    manager = _make_scene_manager(engine, scene_reboot=scene_reboot)

    manager.reboot_to_previous()

    assert scene_reboot.reboot_to_previous_calls == 1


def test_reboot_to_previous_delegates_without_registry_validation() -> None:
    """Unlike reboot_into, no scene name is validated here at all -- the
    recorded return_to is checked at boot by SceneRegistry.resolve_known instead."""
    engine = _make_engine()
    scene_reboot = RecordingSceneReboot()
    manager = _make_scene_manager(engine, scene_registry=SceneRegistry(), scene_reboot=scene_reboot)

    manager.reboot_to_previous()  # must not raise, even with an empty registry

    assert scene_reboot.reboot_to_previous_calls == 1


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
    manager.activate_boot_scene("main")

    manager.update()
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
    scene_reg = _scene_registry(
        ("main", _scene_factory()),
        ("overlay_scene", _scene_factory(settings=_which("overlay"))),
    )
    manager = _make_scene_manager(engine, scene_registry=scene_reg)
    manager.activate_boot_scene("main")
    main_state = manager.active_state

    manager.overlay("overlay_scene")
    manager.update()

    assert engine._update_calls == [main_state], "engine.update must run before the transition"
    assert active_state(manager).settings.get("scene", "which") == "overlay"


def test_last_pending_transition_wins_within_one_tick() -> None:
    engine = _make_engine()
    scene_reg = _scene_registry(
        ("main", _scene_factory()),
        ("scene_a", _scene_factory(settings=_which("a"))),
        ("scene_b", _scene_factory(settings=_which("b"))),
    )
    manager = _make_scene_manager(engine, scene_registry=scene_reg)
    manager.activate_boot_scene("main")

    # Both recorded in one tick — last wins
    manager.overlay("scene_a")
    manager.overlay("scene_b")
    manager.update()

    assert active_state(manager).settings.get("scene", "which") == "b", (
        "last overlay() call in tick should win"
    )


# ---------------------------------------------------------------------------
# SceneManager — boot-scene activation (the boot composition's, not the rules')
# ---------------------------------------------------------------------------


def test_scene_controls_offer_rules_no_way_to_load_a_scene_in_process() -> None:
    assert not hasattr(SceneControls(), "load")


def test_scene_manager_offers_rules_no_way_to_load_a_scene_in_process() -> None:
    manager = _make_scene_manager(_make_engine())

    assert not hasattr(manager, "load")


def test_activating_the_boot_scene_makes_it_active_at_once() -> None:
    scene_reg = _scene_registry(("main", _scene_factory(settings=_which("main"))))
    manager = _make_scene_manager(_make_engine(), scene_registry=scene_reg)

    manager.activate_boot_scene("main")

    assert active_state(manager).settings.get("scene", "which") == "main"


def test_activating_an_unregistered_boot_scene_raises() -> None:
    manager = _make_scene_manager(_make_engine())

    with pytest.raises(ValueError, match="Unknown scene"):
        manager.activate_boot_scene("nonexistent")


def test_activating_a_boot_scene_the_device_cannot_run_raises_and_activates_nothing(
    pack_tree,
) -> None:
    catalog = pack_tree.scan(scenes={"tilt": {"requires": ["accelerometer"]}})
    engine = GameEngine(effect_controls=_RecordingEffectControls(), capabilities=_HAS_BUTTONS)
    manager = _make_scene_manager(engine, scene_registry=catalog.scene_registry)

    with pytest.raises(MissingCapabilityError) as excinfo:
        manager.activate_boot_scene("tilt")

    assert (excinfo.value.scene, excinfo.value.capabilities) == ("tilt", {"accelerometer"})
    assert manager.active_state is None


def test_activating_a_second_boot_scene_raises_and_keeps_the_first() -> None:
    scene_reg = _scene_registry(("first", _scene_factory()), ("second", _scene_factory()))
    manager = _make_scene_manager(_make_engine(), scene_registry=scene_reg)
    manager.activate_boot_scene("first")
    first_state = manager.active_state

    with pytest.raises(ValueError, match="already"):
        manager.activate_boot_scene("second")

    assert manager.active_state is first_state


def test_activating_the_boot_scene_enters_it_with_its_view(pack_tree) -> None:
    catalog = pack_tree.scan(
        effect_packs={"fx": {}},
        scenes={"base": {"effect_packs": [{"name": "fx", "version": "1.0"}], "sounds": ["win"]}},
    )
    admin = SpyEffectAdmin()
    manager = _make_scene_manager(
        _make_engine(),
        rule_registry=catalog.rule_registry,
        scene_registry=catalog.scene_registry,
        effect_admin=admin,
    )

    manager.activate_boot_scene("base")

    ((step, view),) = admin.steps
    assert step == "enter"
    assert view.local_effects is catalog.scene_registry.get("base").local_effect_registry
    assert list(view.local_sounds) == ["win"]
    assert view.declared_packs == frozenset({"fx"})


# ---------------------------------------------------------------------------
# SceneManager — the active boot scene
# ---------------------------------------------------------------------------


def test_the_boot_scenes_state_carries_the_scene_manager_as_scene_controls() -> None:
    engine = _TrackingEngine(_RecordingEffectControls())
    scene_reg = _scene_registry(("main", _scene_factory()))
    manager = _make_scene_manager(engine, scene_registry=scene_reg)
    manager.activate_boot_scene("main")
    manager.update()  # engine.update(active_state)

    assert engine._last_state.scene_controls is manager


def test_the_boot_scenes_state_carries_the_scenes_settings() -> None:
    engine = _TrackingEngine(_RecordingEffectControls())
    settings = _which("main")
    scene_reg = _scene_registry(("main", _scene_factory(settings=settings)))
    manager = _make_scene_manager(engine, scene_registry=scene_reg)
    manager.activate_boot_scene("main")
    manager.update()  # engine.update(active_state); _last_state is now set

    assert engine._last_state.settings is settings


def test_no_transition_stops_effects_through_the_rule_facing_controls() -> None:
    engine, controls = _make_engine_with_controls()
    scene_reg = _scene_registry(("main", _scene_factory()), ("overlay_scene", _scene_factory()))
    manager = _make_scene_manager(engine, scene_registry=scene_reg)

    manager.activate_boot_scene("main")
    manager.overlay("overlay_scene")
    manager.update()
    manager.pop()
    manager.update()

    assert controls.stopped_scopes == []


def test_the_boot_scenes_rules_receive_events(pack_tree) -> None:
    catalog = pack_tree.scan(
        rule_packs={
            "rules": {"rule_a": _GAME_RULE_SOURCE},
            "stubs": {"scene_rule": _GAME_RULE_SOURCE},
        }
    )
    rule_registry = catalog.rule_registry
    engine = _TrackingEngine(_RecordingEffectControls())

    fired: list = []

    pack_rule = rule_registry.get("rules", "rule_a", GameRule)
    pack_rule.on(Event, lambda e, s: fired.append("pack"))

    scene_rule = rule_registry.get("stubs", "scene_rule", GameRule)
    scene_rule.on(Event, lambda e, s: fired.append("scene"))
    scene_reg = _scene_registry(("main", _scene_factory(rule_packs=[_ref("stubs"), _ref("rules")])))
    manager = _make_scene_manager(
        engine,
        rule_registry=rule_registry,
        scene_registry=scene_reg,
    )
    manager.activate_boot_scene("main")
    manager.update()  # engine.update(active_state)

    engine._last_state.queue_event(Event(_GROUP, "verify"))
    manager.update()

    assert "scene" in fired, "scene rule must receive events"
    assert "pack" in fired, "pack rule must receive events"


def test_scene_rules_fire_before_pack_rules(pack_tree) -> None:
    catalog = pack_tree.scan(
        rule_packs={
            "rules": {"rule_a": _GAME_RULE_SOURCE},
            "stubs": {"scene_rule": _GAME_RULE_SOURCE},
        }
    )
    rule_registry = catalog.rule_registry
    engine = _TrackingEngine(_RecordingEffectControls())

    fired: list = []

    pack_rule = rule_registry.get("rules", "rule_a", GameRule)
    pack_rule.on(Event, lambda e, s: fired.append("pack"))

    scene_rule = rule_registry.get("stubs", "scene_rule", GameRule)
    scene_rule.on(Event, lambda e, s: fired.append("scene"))
    scene_reg = _scene_registry(("main", _scene_factory(rule_packs=[_ref("stubs"), _ref("rules")])))
    manager = _make_scene_manager(
        engine,
        rule_registry=rule_registry,
        scene_registry=scene_reg,
    )
    manager.activate_boot_scene("main")
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
        ("base", _scene_factory(settings=_which("base"))),
        ("overlay_scene", _scene_factory(settings=_which("overlay"))),
    )
    manager = _make_scene_manager(engine, scene_registry=scene_reg)

    manager.activate_boot_scene("base")
    manager.update()  # tick on base

    manager.overlay("overlay_scene")
    manager.update()
    manager.update()  # tick on overlay
    assert active_state(manager).settings.get("scene", "which") == "overlay"

    # base was suspended (not cleared): popping restores it
    manager.pop()
    manager.update()
    manager.update()
    assert active_state(manager).settings.get("scene", "which") == "base"


def test_overlay_clears_suspended_base_state_queue_before_pushing(pack_tree) -> None:
    engine = _TrackingEngine(_RecordingEffectControls())
    rule_registry = pack_tree.scan(
        rule_packs={"stubs": {"base_rule": _GAME_RULE_SOURCE}}
    ).rule_registry
    base_events: list = []
    base_rule = rule_registry.get("stubs", "base_rule", GameRule)
    base_rule.on(Event, lambda e, s: base_events.append(e.name))
    scene_reg = _scene_registry(
        ("base", _scene_factory(rule_packs=[_ref("stubs")])),
        ("overlay_scene", _scene_factory()),
    )
    manager = _make_scene_manager(engine, rule_registry=rule_registry, scene_registry=scene_reg)

    manager.activate_boot_scene("base")
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


def test_pop_restores_base_scene_rules_so_events_dispatch_to_base_rules(pack_tree) -> None:
    catalog = pack_tree.scan(
        rule_packs={
            "rules": {"rule_a": _GAME_RULE_SOURCE},
            "stubs": {"base_rule": _GAME_RULE_SOURCE},
        }
    )
    rule_registry = catalog.rule_registry
    engine = _TrackingEngine(_RecordingEffectControls())

    base_events: list = []
    base_rule = rule_registry.get("stubs", "base_rule", GameRule)
    base_rule.on(Event, lambda e, s: base_events.append(e.name))
    pack_rule = rule_registry.get("rules", "rule_a", GameRule)
    pack_events: list = []
    pack_rule.on(Event, lambda e, s: pack_events.append(e.name))

    scene_reg = _scene_registry(
        ("base", _scene_factory(rule_packs=[_ref("stubs"), _ref("rules")])),
        ("overlay_scene", _scene_factory()),
    )
    manager = _make_scene_manager(
        engine,
        rule_registry=rule_registry,
        scene_registry=scene_reg,
    )

    manager.activate_boot_scene("base")
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


def test_pop_clears_restored_state_queue_so_suspended_events_do_not_replay(pack_tree) -> None:
    engine = _TrackingEngine(_RecordingEffectControls())
    rule_registry = pack_tree.scan(
        rule_packs={"stubs": {"base_rule": _GAME_RULE_SOURCE}}
    ).rule_registry
    base_events: list = []
    base_rule = rule_registry.get("stubs", "base_rule", GameRule)
    base_rule.on(Event, lambda e, s: base_events.append(e.name))
    scene_reg = _scene_registry(
        ("base", _scene_factory(rule_packs=[_ref("stubs")])),
        ("overlay_scene", _scene_factory()),
    )
    manager = _make_scene_manager(engine, rule_registry=rule_registry, scene_registry=scene_reg)

    manager.activate_boot_scene("base")
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
        ("base", _scene_factory(settings=_which("base"))),
        ("mid", _scene_factory(settings=_which("mid"))),
        ("top", _scene_factory(settings=_which("top"))),
    )
    manager = _make_scene_manager(engine, scene_registry=scene_reg)

    manager.activate_boot_scene("base")
    manager.overlay("mid")
    manager.update()
    manager.overlay("top")
    manager.update()
    manager.update()  # tick on top

    manager.pop()
    manager.update()
    manager.update()  # tick on restored scene

    assert active_state(manager).settings.get("scene", "which") == "mid", (
        "pop from 3-layer stack must restore the scene directly below"
    )

    manager.pop()
    manager.update()
    manager.update()

    assert active_state(manager).settings.get("scene", "which") == "base"


# ---------------------------------------------------------------------------
# SceneManager — a covered scene's game time stops
# ---------------------------------------------------------------------------

_STEP = 0.25
"""Seconds each tick of a ``_SteppingTimer`` lasts: exact in binary, so sums compare exactly."""


class _SteppingTimer(Timer):
    """An engine clock whose every tick lasts exactly ``_STEP`` seconds."""

    def update(self) -> None:
        self.elapsed = _STEP
        self.total += _STEP


def _covered_scene_manager(rule_registry: PackRegistry | None = None, rule_packs=()):
    """A SceneManager on a ``_SteppingTimer`` with ``base`` (running *rule_packs*) and ``pause``."""
    engine = GameEngine(effect_controls=_RecordingEffectControls(), timer=_SteppingTimer())
    scene_reg = _scene_registry(
        ("base", _scene_factory(rule_packs=list(rule_packs))),
        ("pause", _scene_factory()),
    )
    return _make_scene_manager(engine, rule_registry=rule_registry, scene_registry=scene_reg)


def _tick(manager: SceneManager, ticks: int) -> None:
    for _ in range(ticks):
        manager.update()


def test_a_covered_scenes_game_time_stops_while_covered() -> None:
    manager = _covered_scene_manager()
    manager.activate_boot_scene("base")
    base_state = manager.active_state
    _tick(manager, 4)

    manager.overlay("pause")
    _tick(manager, 1)  # base's last tick; the overlay arrives at its end
    covered_at = base_state.total
    _tick(manager, 10)

    assert base_state.total == covered_at == 5 * _STEP


def test_after_pop_a_covered_scenes_game_time_continues_from_where_it_stopped() -> None:
    manager = _covered_scene_manager()
    manager.activate_boot_scene("base")
    base_state = manager.active_state
    _tick(manager, 4)
    manager.overlay("pause")
    _tick(manager, 1)
    _tick(manager, 10)

    manager.pop()
    _tick(manager, 1)  # the overlay's last tick; the pop applies at its end
    _tick(manager, 3)

    assert base_state.total == (5 + 3) * _STEP


def test_a_covered_scenes_first_tick_after_pop_has_an_ordinary_elapsed() -> None:
    manager = _covered_scene_manager()
    manager.activate_boot_scene("base")
    base_state = manager.active_state
    manager.overlay("pause")
    _tick(manager, 1)
    _tick(manager, 10)
    manager.pop()
    _tick(manager, 1)

    _tick(manager, 1)

    assert base_state.elapsed == _STEP


_PHASE_ELAPSED_RULE = """\
from engine.events import Event
from engine.phase import PhaseKey, PhaseRule, PhaseSlot

_PHASE = PhaseKey("timed")
_SLOT = PhaseSlot("timed_machine", _PHASE)


class _RecordsPhaseElapsed(PhaseRule):
    def __init__(self) -> None:
        super().__init__(_PHASE, _SLOT)
        self.on(Event, self._record)

    def _record(self, event, state) -> None:
        state.set("phase_elapsed", _SLOT(state).elapsed(state.total))


RULE = _RecordsPhaseElapsed()
"""


def test_a_phases_elapsed_time_excludes_the_time_its_scene_spent_covered(pack_tree) -> None:
    rule_registry = pack_tree.scan(
        rule_packs={"timed": {"rule": _PHASE_ELAPSED_RULE}}
    ).rule_registry
    manager = _covered_scene_manager(rule_registry, rule_packs=[_ref("timed")])
    manager.activate_boot_scene("base")
    base_state = manager.active_state
    _tick(manager, 4)
    manager.overlay("pause")
    _tick(manager, 1)
    _tick(manager, 10)
    manager.pop()
    _tick(manager, 1)
    _tick(manager, 2)

    base_state.queue_event(Event(_GROUP, "tick"))
    _tick(manager, 1)

    assert base_state.get("phase_elapsed", -1.0) == (5 + 3) * _STEP


def test_an_overlays_game_time_starts_when_the_overlay_arrives() -> None:
    manager = _covered_scene_manager()
    manager.activate_boot_scene("base")
    _tick(manager, 4)
    manager.overlay("pause")
    _tick(manager, 1)

    _tick(manager, 3)

    assert manager.active_state.total == 3 * _STEP


# ---------------------------------------------------------------------------
# SceneManager — rule pack integration
# ---------------------------------------------------------------------------


def test_rule_pack_items_all_receive_events_after_load(pack_tree) -> None:
    rule_content = "from engine.engine import GameRule\nRULE = GameRule()\n"
    catalog = pack_tree.scan(
        rule_packs={
            "rules": {
                "rule_a": rule_content,
                "rule_b": rule_content,
            },
            "stubs": {"scene_rule": rule_content},
        }
    )
    rule_registry = catalog.rule_registry
    engine = _TrackingEngine(_RecordingEffectControls())

    fired_by: list = []

    pack_rule_a = rule_registry.get("rules", "rule_a", GameRule)
    pack_rule_b = rule_registry.get("rules", "rule_b", GameRule)
    pack_rule_a.on(Event, lambda e, s: fired_by.append("pack_a"))
    pack_rule_b.on(Event, lambda e, s: fired_by.append("pack_b"))

    scene_rule = rule_registry.get("stubs", "scene_rule", GameRule)
    scene_rule.on(Event, lambda e, s: fired_by.append("scene"))
    scene_reg = _scene_registry(("main", _scene_factory(rule_packs=[_ref("stubs"), _ref("rules")])))
    manager = _make_scene_manager(
        engine,
        rule_registry=rule_registry,
        scene_registry=scene_reg,
    )
    manager.activate_boot_scene("main")
    manager.update()  # engine.update(active_state)

    engine._last_state.queue_event(Event(_GROUP, "verify"))
    manager.update()

    assert "scene" in fired_by, "scene rule must fire"
    assert "pack_a" in fired_by, "pack rule_a must fire"
    assert "pack_b" in fired_by, "pack rule_b must fire"


def test_rule_pack_items_loaded_in_alphabetical_order(pack_tree) -> None:
    rule_template = (
        "from engine.engine import GameRule\nimport engine.scene as _s\nRULE = GameRule()\n"
    )
    rule_registry = pack_tree.scan(
        rule_packs={
            "rules": {
                "z_rule": rule_template,
                "a_rule": rule_template,
                "m_rule": rule_template,
            }
        }
    ).rule_registry

    # Verify items() returns alphabetical order
    items = rule_registry.items("rules")
    assert items == sorted(items)


_FLAGGING_RULE = """\
from engine.engine import GameRule
from engine.events import Event


class _Flag(GameRule):
    def __init__(self) -> None:
        self.on(Event, lambda event, state: state.set("card_pack_rule_ran", True))


RULE = _Flag()
"""


def test_a_flash_scene_runs_a_rule_from_a_card_rule_pack(pack_tree) -> None:
    flash = pack_tree.root("tc_flash")
    card = pack_tree.root("tc_card")
    pack_tree.rule_pack(card, "card_pack", items={"flag": _FLAGGING_RULE})
    pack_tree.scene(flash, "lobby", rule_packs=[{"name": "card_pack", "version": "1.0"}])
    catalog = pack_tree.scan_roots(flash, card)
    manager = _make_scene_manager(
        _make_engine(),
        rule_registry=catalog.rule_registry,
        scene_registry=catalog.scene_registry,
    )
    manager.activate_boot_scene("lobby")
    state = active_state(manager)

    state.queue_event(Event(_GROUP, "ping"))
    manager.update()

    assert state.get_or_none("card_pack_rule_ran", bool) is True


# ---------------------------------------------------------------------------
# SceneManager — GC eligibility after full unload
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# SceneManager — activation invariant pin
# ---------------------------------------------------------------------------


def test_pop_activates_revealed_entry_with_both_rules_and_its_view(pack_tree) -> None:
    """After boot → overlay → pop, the revealed entry has rules on the engine
    AND its own view handed to uncover (invariant: no half-activation)."""
    engine = _make_engine()
    base_local_registry = Scene(effect_packs=[], rule_packs=[]).local_effect_registry
    rule_registry = pack_tree.scan(
        rule_packs={"stubs": {"base_rule": _GAME_RULE_SOURCE}}
    ).rule_registry
    base_rule = rule_registry.get("stubs", "base_rule", GameRule)

    base_events: list = []
    base_rule.on(Event, lambda e, s: base_events.append(e.name))

    def base_factory():
        return Scene(
            effect_packs=[],
            rule_packs=[_ref("stubs")],
            local_effect_registry=base_local_registry,
        )

    scene_reg = SceneRegistry()
    scene_reg.register("base", base_factory)
    scene_reg.register("overlay_scene", _scene_factory())
    admin = SpyEffectAdmin()
    manager = _make_scene_manager(
        engine, rule_registry=rule_registry, scene_registry=scene_reg, effect_admin=admin
    )

    manager.activate_boot_scene("base")
    manager.overlay("overlay_scene")
    manager.update()

    manager.pop()
    manager.update()

    active_state(manager).queue_event(Event(_GROUP, "check"))
    manager.update()
    assert base_events, "base rules must be active on the engine after pop"
    assert admin.steps[-1][1].local_effects is base_local_registry


def test_each_transition_makes_one_effect_admin_step_carrying_the_top_scenes_view(
    pack_tree,
) -> None:
    catalog = pack_tree.scan(effect_packs={"fx": {}, "gfx": {}})
    scene_reg = _scene_registry(
        ("base", _scene_factory(effect_packs=[_ref("fx")])),
        ("overlay_scene", _scene_factory(effect_packs=[_ref("gfx")])),
    )
    admin = SpyEffectAdmin()
    manager = _make_scene_manager(
        _make_engine(),
        rule_registry=catalog.rule_registry,
        scene_registry=scene_reg,
        effect_admin=admin,
    )

    manager.activate_boot_scene("base")
    manager.overlay("overlay_scene")
    manager.update()
    manager.pop()
    manager.update()

    assert [(step, view.declared_packs) for step, view in admin.steps] == [
        ("enter", frozenset({"fx"})),
        ("cover", frozenset({"gfx"})),
        ("uncover", frozenset({"fx"})),
    ]


def test_pop_hands_back_the_bundle_its_overlay_set_aside() -> None:
    scene_reg = _scene_registry(
        ("base", _scene_factory()), ("mid", _scene_factory()), ("top", _scene_factory())
    )
    admin = SpyEffectAdmin()
    manager = _make_scene_manager(_make_engine(), scene_registry=scene_reg, effect_admin=admin)
    manager.activate_boot_scene("base")
    manager.overlay("mid")
    manager.update()
    manager.overlay("top")
    manager.update()

    manager.pop()
    manager.update()
    manager.pop()
    manager.update()

    under_mid, under_top = admin.covered
    assert admin.uncovered[0] is under_top
    assert admin.uncovered[1] is under_mid


def test_uncovering_carries_the_covered_scenes_whole_view(pack_tree) -> None:
    catalog = pack_tree.scan(
        effect_packs={"fx": {}, "gfx": {}},
        scenes={
            "base": {"effect_packs": [{"name": "fx", "version": "1.0"}], "sounds": ["win"]},
            "overlay_scene": {
                "effect_packs": [{"name": "gfx", "version": "1.0"}],
                "sounds": ["lose"],
            },
        },
    )
    admin = SpyEffectAdmin()
    manager = _make_scene_manager(
        _make_engine(),
        rule_registry=catalog.rule_registry,
        scene_registry=catalog.scene_registry,
        effect_admin=admin,
    )
    manager.activate_boot_scene("base")
    manager.overlay("overlay_scene")
    manager.update()

    manager.pop()
    manager.update()

    step, view = admin.steps[-1]
    assert step == "uncover"
    assert view.local_effects is catalog.scene_registry.get("base").local_effect_registry
    assert list(view.local_sounds) == ["win"]
    assert view.declared_packs == frozenset({"fx"})


# ---------------------------------------------------------------------------
# SceneManager — resolution-failure ordering
# ---------------------------------------------------------------------------


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

    manager.activate_boot_scene("base")

    ref = weakref.ref(created_scene)
    created_scene = None

    manager.overlay("overlay_scene")
    manager.update()

    gc.collect()
    assert ref() is not None, "Suspended scene should remain on stack (not GC'd)"


# ---------------------------------------------------------------------------
# Merge strategies and effects across an Overlay, through the SceneRuntime (issue #587)
# ---------------------------------------------------------------------------


class _Act(Event):
    """An event whose handler runs *action* on the active scene's ``EffectControls``.

    The handler stores what *action* returned in ``result``.
    """

    __slots__ = ("action", "result")

    def __init__(self, action) -> None:
        super().__init__(_GROUP, "act")
        self.action = action
        self.result = None


def _run_act(event: _Act, state: GameState) -> None:
    event.result = event.action(state.effect_controls)


class _MergeStrategyRig:
    """A SceneRuntime over solid-fill 'red'/'blue' effects, drawn on one PERSONAL output.

    Every scene declares the 'color' pack and runs its own rule, which
    answers ``act`` by running the given action on that scene's
    ``EffectControls``.
    """

    def __init__(self, pack_tree, scene_names) -> None:
        catalog = pack_tree.scan(
            effect_packs={"color": _COLOR_EFFECTS},
            rule_packs={name + "_rules": {"rule": _GAME_RULE_SOURCE} for name in scene_names},
            scenes={
                name: {
                    "effect_packs": [{"name": "color", "version": "1.0"}],
                    "rule_packs": [{"name": name + "_rules", "version": "1.0"}],
                }
                for name in scene_names
            },
        )
        for name in scene_names:
            catalog.rule_registry.get(name + "_rules", "rule", GameRule).on(_Act, _run_act)
        self.output = SpyEffectOutput(min_resolution=10, scopes=[Scope.PERSONAL])
        self.runtime = make_scene_runtime(catalog, [self.output])
        self.runtime.activate_boot_scene(scene_names[0])

    def act(self, action):
        """Run *action* on the top scene's ``EffectControls`` in one tick; return its result."""
        event = _Act(action)
        self.runtime.queue_event(event)
        self.runtime.update()
        return event.result

    def overlay(self, name: str) -> None:
        self.runtime.scene_controls.overlay(name)
        self.runtime.update()

    def pop(self) -> None:
        self.runtime.scene_controls.pop()
        self.runtime.update()

    def tick(self) -> None:
        self.runtime.update()

    def drawn(self) -> list:
        """The pixels composed on the output's last draw."""
        _, composed = self.output.update_pixels_calls[-1]
        return list(composed)

    def fill_personal(self) -> list:
        """Add fresh red+blue effects to PERSONAL in one tick; return the composed pixels."""

        def add_red_and_blue(controls: EffectControls) -> None:
            controls.add_effect(Scope.PERSONAL, "color.red", {})
            controls.add_effect(Scope.PERSONAL, "color.blue", {})

        self.act(add_red_and_blue)
        return self.drawn()


def _set_merge_strategy(strategy):
    return lambda controls: controls.set_merge_strategy(Scope.PERSONAL, strategy)


def _set_effect(name: str):
    return lambda controls: controls.set_effect(Scope.PERSONAL, name, {})


_SPLIT_RED_BLUE = [0xFF0000] * 5 + [0x0000FF] * 5
_ADDITIVE_RED_BLUE = [0xFF00FF] * 10


def test_an_overlay_starts_on_split_whatever_the_covered_scene_chose(pack_tree) -> None:
    rig = _MergeStrategyRig(pack_tree, ["base", "overlay_scene"])
    rig.act(_set_merge_strategy(ADDITIVE))

    rig.overlay("overlay_scene")

    assert rig.fill_personal() == _SPLIT_RED_BLUE


def test_pop_restores_the_covered_scenes_additive_merge_strategy(pack_tree) -> None:
    rig = _MergeStrategyRig(pack_tree, ["base", "overlay_scene"])
    rig.act(_set_merge_strategy(ADDITIVE))
    rig.overlay("overlay_scene")

    rig.pop()

    assert rig.fill_personal() == _ADDITIVE_RED_BLUE


def test_while_covered_the_covered_scenes_effects_are_not_drawn(pack_tree) -> None:
    rig = _MergeStrategyRig(pack_tree, ["base", "overlay_scene"])
    rig.act(_set_effect("color.red"))

    rig.overlay("overlay_scene")
    rig.output.update_pixels_calls.clear()
    rig.tick()

    assert rig.output.update_pixels_calls == []


def test_after_pop_the_covered_scenes_effects_are_drawn_again_under_the_same_receipt(
    pack_tree,
) -> None:
    rig = _MergeStrategyRig(pack_tree, ["base", "overlay_scene"])
    receipt = rig.act(_set_effect("color.red"))
    rig.overlay("overlay_scene")
    rig.act(_set_effect("color.blue"))  # the overlay's own

    rig.pop()
    receipt.brightness = 0.5
    rig.tick()

    assert rig.drawn() == [0x7F0000] * 10


def test_an_overlays_stop_on_every_scope_leaves_the_covered_scenes_effects(pack_tree) -> None:
    rig = _MergeStrategyRig(pack_tree, ["base", "overlay_scene"])
    rig.act(_set_effect("color.red"))
    rig.overlay("overlay_scene")

    rig.act(lambda controls: controls.stop_effect(Scope.ALL))
    rig.pop()

    assert rig.drawn() == [0xFF0000] * 10


def test_stacked_overlays_each_give_back_the_scene_directly_beneath(pack_tree) -> None:
    rig = _MergeStrategyRig(pack_tree, ["base", "mid", "top"])
    rig.act(_set_effect("color.red"))
    rig.overlay("mid")
    rig.act(_set_effect("color.blue"))
    rig.overlay("top")

    rig.pop()
    mid_pixels = rig.drawn()
    rig.pop()

    assert mid_pixels == [0x0000FF] * 10
    assert rig.drawn() == [0xFF0000] * 10


def test_scene_overlay_merge_strategy_change_takes_effect_the_next_tick(pack_tree) -> None:
    rig = _MergeStrategyRig(pack_tree, ["base", "overlay_scene"])
    rig.overlay("overlay_scene")
    assert rig.fill_personal() == _SPLIT_RED_BLUE

    rig.act(_set_merge_strategy(ADDITIVE))

    assert rig.drawn() == _ADDITIVE_RED_BLUE, (
        "a set_merge_strategy call during an overlay must apply from its very next tick"
    )


def test_scene_pop_restores_pre_overlay_merge_strategy_discarding_overlay_changes(
    pack_tree,
) -> None:
    rig = _MergeStrategyRig(pack_tree, ["base", "overlay_scene"])
    rig.overlay("overlay_scene")
    rig.act(_set_merge_strategy(ADDITIVE))  # overlay-only change

    rig.pop()

    assert rig.fill_personal() == _SPLIT_RED_BLUE, (
        "pop must restore base's pre-overlay Split choice, discarding the overlay's Additive"
    )


def test_nested_overlay_pop_merge_strategy_change_never_leaks_past_its_own_pop(
    pack_tree,
) -> None:
    rig = _MergeStrategyRig(pack_tree, ["base", "mid", "top"])

    rig.overlay("mid")
    rig.act(_set_merge_strategy(ADDITIVE))  # mid's own choice

    rig.overlay("top")
    rig.act(_set_merge_strategy(SPLIT))  # top-only change

    rig.pop()  # leave top; discard top's change, restore mid's Additive
    assert rig.fill_personal() == _ADDITIVE_RED_BLUE, (
        "mid's Additive choice must survive popping the nested top overlay"
    )

    rig.pop()  # leave mid; discard mid's change, restore base's original Split
    assert rig.fill_personal() == _SPLIT_RED_BLUE, (
        "base's original Split choice must be restored once every overlay above it is popped"
    )


# ---------------------------------------------------------------------------
# SceneManager — every transition into a scene checks its Required capabilities
# ---------------------------------------------------------------------------

_HAS_BUTTONS = frozenset(("button.A", "button.B"))


def _capability_manager(pack_tree, scene_reboot: SceneReboot | None = None) -> SceneManager:
    """A manager on a device with only buttons A and B, whose ``home`` scene is active.

    ``home`` requires nothing; ``tilt`` requires the accelerometer the device lacks.
    """
    catalog = pack_tree.scan(scenes={"home": {}, "tilt": {"requires": ["accelerometer"]}})
    engine = GameEngine(effect_controls=_RecordingEffectControls(), capabilities=_HAS_BUTTONS)
    manager = _make_scene_manager(
        engine, scene_registry=catalog.scene_registry, scene_reboot=scene_reboot
    )
    manager.activate_boot_scene("home")
    return manager


def test_scene_controls_can_run_raises_not_implemented_error() -> None:
    with pytest.raises(NotImplementedError):
        SceneControls().can_run("any")


def test_scene_reboot_previous_scene_raises_not_implemented_error() -> None:
    with pytest.raises(NotImplementedError):
        SceneReboot().previous_scene()


def test_can_run_a_scene_whose_required_capabilities_the_device_has(pack_tree):
    manager = _capability_manager(pack_tree)

    assert manager.can_run("home")


def test_cannot_run_a_scene_requiring_a_capability_the_device_lacks(pack_tree):
    manager = _capability_manager(pack_tree)

    assert not manager.can_run("tilt")


def test_can_run_raises_for_an_unknown_scene(pack_tree):
    manager = _capability_manager(pack_tree)

    with pytest.raises(ValueError, match="nonexistent"):
        manager.can_run("nonexistent")


def test_an_overlay_of_a_scene_the_device_cannot_run_raises(pack_tree):
    manager = _capability_manager(pack_tree)

    with pytest.raises(MissingCapabilityError) as excinfo:
        manager.overlay("tilt")

    assert (excinfo.value.scene, excinfo.value.capabilities) == ("tilt", {"accelerometer"})


def test_a_refused_overlay_leaves_the_active_scene_in_place(pack_tree):
    manager = _capability_manager(pack_tree)
    before = manager.active_state

    with pytest.raises(MissingCapabilityError):
        manager.overlay("tilt")
    manager.update()

    assert manager.active_state is before


def test_reboot_into_a_scene_the_device_cannot_run_raises_and_never_reaches_the_port(pack_tree):
    scene_reboot = RecordingSceneReboot()
    manager = _capability_manager(pack_tree, scene_reboot)

    with pytest.raises(MissingCapabilityError) as excinfo:
        manager.reboot_into("tilt")

    assert excinfo.value.scene == "tilt"
    assert scene_reboot.reboot_into_calls == []


def test_reboot_to_previous_into_a_scene_the_device_cannot_run_raises_and_never_reaches_the_port(
    pack_tree,
):
    scene_reboot = RecordingSceneReboot(previous="tilt")
    manager = _capability_manager(pack_tree, scene_reboot)

    with pytest.raises(MissingCapabilityError) as excinfo:
        manager.reboot_to_previous()

    assert excinfo.value.scene == "tilt"
    assert scene_reboot.reboot_to_previous_calls == 0


def test_reboot_to_previous_into_a_scene_the_device_can_run_reaches_the_port(pack_tree):
    scene_reboot = RecordingSceneReboot(previous="home")
    manager = _capability_manager(pack_tree, scene_reboot)

    manager.reboot_to_previous()

    assert scene_reboot.reboot_to_previous_calls == 1
