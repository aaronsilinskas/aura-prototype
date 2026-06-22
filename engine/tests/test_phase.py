"""Behaviour tests for the phase-machine engine primitive.

Lifecycle behaviour (``on_enter`` / handler / ``on_exit``) is exercised
through the real ``GameEngine.update`` + ``SpyEffectControls`` seam using
throwaway rule subclasses that emit a uniquely-named effect at each lifecycle
point.  Tests assert on those observable effects only — never on the machine's
private entry flag.
"""

from __future__ import annotations

import pytest

from engine.engine import GameEngine
from engine.events import Event, EventGroup
from engine.phase import (
    InPhaseRule,
    PhaseKey,
    PhaseMachine,
    PhaseRule,
)
from engine.state import GameState, SceneControls, Scope, StateSlot
from engine.tests.helpers import SpyEffectControls

_GROUP = EventGroup("phase_test")


class _TickEvent(Event):
    __slots__ = ()

    def __init__(self) -> None:
        super().__init__(_GROUP, "tick")


_PHASE_A = PhaseKey("a")
_PHASE_B = PhaseKey("b")
_MACHINE_KEY = "test_machine"


# ---------------------------------------------------------------------------
# Throwaway rules: each emits a uniquely-named effect per lifecycle point
# ---------------------------------------------------------------------------


class _LifecycleRule(PhaseRule):
    """PhaseRule that emits ``enter:``/``tick:``/``exit:`` effects, optionally transitioning."""

    def __init__(
        self,
        phase: PhaseKey,
        label: str,
        machine_key: str = _MACHINE_KEY,
        initial: PhaseKey = _PHASE_A,
        transitions_to: PhaseKey | None = None,
    ) -> None:
        super().__init__(phase, machine_key, initial)
        self._label = label
        self._transitions_to = transitions_to
        self.on(_TickEvent, self._tick)

    def on_enter(self, state: GameState) -> None:
        state.effect_controls.add_effect(Scope.PERSONAL, "enter:" + self._label, {})

    def on_exit(self, state: GameState) -> None:
        state.effect_controls.add_effect(Scope.PERSONAL, "exit:" + self._label, {})

    def _tick(self, event: _TickEvent, state: GameState) -> None:
        state.effect_controls.add_effect(Scope.PERSONAL, "tick:" + self._label, {})
        if self._transitions_to is not None:
            self.transition_to(state, self._transitions_to)
            self._transitions_to = None


class _InPhaseEmitter(InPhaseRule):
    """InPhaseRule that emits an ``in:`` effect each tick its phase is active."""

    def __init__(
        self,
        phase: PhaseKey,
        label: str,
        machine_key: str = _MACHINE_KEY,
        initial: PhaseKey = _PHASE_A,
    ) -> None:
        super().__init__(phase, machine_key, initial)
        self._label = label
        self.on(_TickEvent, self._tick)

    def _tick(self, event: _TickEvent, state: GameState) -> None:
        state.effect_controls.add_effect(Scope.PERSONAL, "in:" + self._label, {})


def _run(rules: list, ticks: int) -> list[str]:
    """Run *rules* through *ticks* engine updates; return emitted effect names in order."""
    spy = SpyEffectControls()
    engine = GameEngine(effect_controls=spy)
    state = engine.create_state(SceneControls())
    engine.set_rules(rules)
    for _ in range(ticks):
        state.queue_event(_TickEvent())
        engine.update(state)
    return [name for _, name, _ in spy.add_effect_calls]


# ---------------------------------------------------------------------------
# PhaseKey — identity typing
# ---------------------------------------------------------------------------


def test_phase_key_never_equals_a_bare_string() -> None:
    machine = PhaseMachine(_PHASE_A)

    assert (machine.phase == "a") is False
    assert machine.phase != "a"


def test_distinct_phase_keys_with_the_same_name_are_not_equal() -> None:
    assert PhaseKey("ready") != PhaseKey("ready")


# ---------------------------------------------------------------------------
# PhaseMachine — enter / elapsed
# ---------------------------------------------------------------------------


def test_enter_sets_phase_and_phase_start_and_raises_the_entry_flag() -> None:
    machine = PhaseMachine(_PHASE_A)
    machine.take_just_entered()  # consume the initial flag

    machine.enter(_PHASE_B, now=4.0)

    assert machine.phase is _PHASE_B
    assert machine.phase_start == 4.0
    assert machine.take_just_entered() is True


def test_elapsed_reports_the_gap_since_entry() -> None:
    machine = PhaseMachine(_PHASE_A)
    machine.enter(_PHASE_B, now=10.0)

    assert machine.elapsed(now=13.5) == pytest.approx(3.5)


def test_take_just_entered_returns_true_once_then_false() -> None:
    machine = PhaseMachine(_PHASE_A)

    assert machine.take_just_entered() is True
    assert machine.take_just_entered() is False


# ---------------------------------------------------------------------------
# PhaseRule lifecycle through the engine seam
# ---------------------------------------------------------------------------


def test_on_enter_fires_once_while_the_gated_handler_fires_every_tick() -> None:
    rule = _LifecycleRule(_PHASE_A, "owner")

    names = _run([rule], ticks=3)

    assert names == ["enter:owner", "tick:owner", "tick:owner", "tick:owner"]


def test_on_exit_fires_on_transition_and_the_next_phase_enters() -> None:
    leaving = _LifecycleRule(_PHASE_A, "a", transitions_to=_PHASE_B)
    arriving = _LifecycleRule(_PHASE_B, "b")

    names = _run([leaving, arriving], ticks=2)

    # tick1: A enters and ticks, then transitions out (exit on A); because B is
    # registered after A it sees the new phase within the same tick and enters.
    # tick2: only B is active and ticks again.
    assert names == ["enter:a", "tick:a", "exit:a", "enter:b", "tick:b", "tick:b"]


def test_handler_does_not_fire_after_its_phase_is_left() -> None:
    leaving = _LifecycleRule(_PHASE_A, "a", transitions_to=_PHASE_B)
    arriving = _LifecycleRule(_PHASE_B, "b")

    names = _run([leaving, arriving], ticks=4)

    assert "tick:a" in names
    assert names.count("tick:a") == 1  # only the entry tick, never after leaving A


@pytest.mark.parametrize("owner_dispatches_first", [True, False])
def test_on_enter_fires_exactly_once_regardless_of_dispatch_order(
    owner_dispatches_first: bool,
) -> None:
    # Whether the arriving owner sorts before or after the transitioning rule,
    # its on_enter must fire exactly once: same tick if it dispatches after the
    # transition, otherwise the following tick (the entry flag persists).
    leaving = _LifecycleRule(_PHASE_A, "a", transitions_to=_PHASE_B)
    arriving = _LifecycleRule(_PHASE_B, "b")
    rules = [arriving, leaving] if owner_dispatches_first else [leaving, arriving]

    names = _run(rules, ticks=4)

    assert names.count("enter:b") == 1


# ---------------------------------------------------------------------------
# InPhaseRule — phase-gated, no lifecycle, shareable
# ---------------------------------------------------------------------------


def test_in_phase_rule_handler_fires_only_while_its_phase_is_active() -> None:
    # bystander registered first so it dispatches before the transition each
    # tick: it must not catch the same-tick switch into B on the transition tick.
    bystander = _InPhaseEmitter(_PHASE_B, "bystander")
    leaving = _LifecycleRule(_PHASE_A, "a", transitions_to=_PHASE_B)

    names = _run([bystander, leaving], ticks=4)

    # A is active on tick1 only; B is active from tick2 on (3 remaining ticks).
    assert names.count("in:bystander") == 3
    # The bystander never emits while A is the active phase.
    assert names.index("in:bystander") > names.index("tick:a")


def test_in_phase_rule_does_not_consume_the_entry_flag_for_a_phase_owner() -> None:
    # InPhaseRule registered first so it dispatches before the owner each tick;
    # if it consumed the entry flag, the owner's on_enter would never fire.
    bystander = _InPhaseEmitter(_PHASE_A, "bystander", initial=_PHASE_A)
    owner = _LifecycleRule(_PHASE_A, "owner", initial=_PHASE_A)

    names = _run([bystander, owner], ticks=2)

    assert names.count("enter:owner") == 1


def test_multiple_in_phase_rules_share_one_phase() -> None:
    first = _InPhaseEmitter(_PHASE_A, "first", initial=_PHASE_A)
    second = _InPhaseEmitter(_PHASE_A, "second", initial=_PHASE_A)

    names = _run([first, second], ticks=1)

    assert "in:first" in names
    assert "in:second" in names


def test_in_phase_rule_and_phase_rule_coexist_on_one_phase() -> None:
    owner = _LifecycleRule(_PHASE_A, "owner", initial=_PHASE_A)
    bystander = _InPhaseEmitter(_PHASE_A, "bystander", initial=_PHASE_A)

    names = _run([owner, bystander], ticks=1)

    assert names == ["enter:owner", "tick:owner", "in:bystander"]


# ---------------------------------------------------------------------------
# Duplicate-owner fail-fast at scene load (GameEngine.set_rules)
# ---------------------------------------------------------------------------


def test_two_phase_rules_owning_the_same_machine_and_phase_fail_at_load() -> None:
    engine = GameEngine(effect_controls=SpyEffectControls())
    one = _LifecycleRule(_PHASE_A, "one")
    two = _LifecycleRule(_PHASE_A, "two")

    with pytest.raises(ValueError):
        engine.set_rules([one, two])


def test_phase_rules_on_different_phases_load_cleanly() -> None:
    engine = GameEngine(effect_controls=SpyEffectControls())
    a = _LifecycleRule(_PHASE_A, "a")
    b = _LifecycleRule(_PHASE_B, "b")

    engine.set_rules([a, b])  # does not raise

    assert len(engine.rules) == 2


def test_same_phase_under_different_machine_keys_loads_cleanly() -> None:
    engine = GameEngine(effect_controls=SpyEffectControls())
    one = _LifecycleRule(_PHASE_A, "one", machine_key="machine_one")
    two = _LifecycleRule(_PHASE_A, "two", machine_key="machine_two")

    engine.set_rules([one, two])  # does not raise

    assert len(engine.rules) == 2


def test_in_phase_rule_sharing_a_phase_with_its_owner_is_not_a_duplicate() -> None:
    engine = GameEngine(effect_controls=SpyEffectControls())
    owner = _LifecycleRule(_PHASE_A, "owner")
    bystander = _InPhaseEmitter(_PHASE_A, "bystander")

    engine.set_rules([owner, bystander])  # does not raise

    assert len(engine.rules) == 2


# ---------------------------------------------------------------------------
# PhaseRule per-instance StateSlot — slot identity and phase_ownership
# ---------------------------------------------------------------------------


def test_phase_rule_phase_ownership_returns_slot_key_and_phase() -> None:
    rule = _LifecycleRule(_PHASE_A, "owner", machine_key=_MACHINE_KEY)

    key, phase = rule.phase_ownership()

    assert key == _MACHINE_KEY
    assert phase is _PHASE_A


def test_module_level_slot_and_rule_per_instance_slot_same_key_resolve_same_machine() -> None:
    # A module-level StateSlot (simulating tag_phase / rlgl_phase) and the rule's
    # own per-instance slot both keyed to _MACHINE_KEY must resolve the identical
    # cached PhaseMachine from the same GameState.
    module_slot: StateSlot = StateSlot(_MACHINE_KEY, lambda s: PhaseMachine(_PHASE_A), PhaseMachine)
    rule = _LifecycleRule(_PHASE_A, "owner", machine_key=_MACHINE_KEY)

    state = GameState(SpyEffectControls(), SceneControls())

    via_module_slot = module_slot(state)
    via_rule = rule._machine(state)  # testing internal seam deliberately

    assert via_module_slot is via_rule
