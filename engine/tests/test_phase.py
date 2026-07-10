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
    PhaseSlot,
)
from engine.state import GameState, SceneControls, Scope
from engine.tests.helpers import SpyEffectControls

_GROUP = EventGroup("phase_test")


class _TickEvent(Event):
    __slots__ = ()

    def __init__(self) -> None:
        super().__init__(_GROUP, "tick")


_PHASE_A = PhaseKey("a")
_PHASE_B = PhaseKey("b")
_MACHINE_KEY = "test_machine"
_DEFAULT_SLOT = PhaseSlot(_MACHINE_KEY, _PHASE_A)


# ---------------------------------------------------------------------------
# Throwaway rules: each emits a uniquely-named effect per lifecycle point
# ---------------------------------------------------------------------------


class _LifecycleRule(PhaseRule):
    """PhaseRule that emits ``enter:``/``tick:``/``exit:`` effects, optionally transitioning."""

    def __init__(
        self,
        phase: PhaseKey,
        label: str,
        phase_slot: PhaseSlot = _DEFAULT_SLOT,
        transitions_to: PhaseKey | None = None,
    ) -> None:
        super().__init__(phase, phase_slot)
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
        phase_slot: PhaseSlot = _DEFAULT_SLOT,
    ) -> None:
        super().__init__(phase, phase_slot)
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


def _rule_machine(rule: _LifecycleRule, state: GameState) -> PhaseMachine:
    """Dedicated helper: expose a rule's internal machine for seam-level identity tests."""
    return rule._machine(state)


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
# PhaseSlot — lazy get-or-create accessor, shared by construction
# ---------------------------------------------------------------------------


def test_phase_slot_creates_a_machine_at_the_initial_phase_on_first_call() -> None:
    slot = PhaseSlot("some_machine", _PHASE_A)
    state = GameState(SpyEffectControls(), SceneControls())

    machine = slot(state)

    assert machine.phase is _PHASE_A


def test_phase_slot_returns_the_same_cached_machine_on_repeated_calls() -> None:
    slot = PhaseSlot("some_machine", _PHASE_A)
    state = GameState(SpyEffectControls(), SceneControls())

    first = slot(state)
    second = slot(state)

    assert first is second


def test_phase_slot_exposes_its_key() -> None:
    slot = PhaseSlot("some_machine", _PHASE_A)

    assert slot.key == "some_machine"


def test_two_phase_slots_with_the_same_key_still_resolve_the_same_cached_machine() -> None:
    # Lazy get-or-create means any two PhaseSlots keyed alike reach the one
    # cached PhaseMachine already stored under that key in GameState -- there
    # is no "unestablished key" failure. Identity divergence is instead caught
    # at scene load by _check_phase_owners (see the engine.py tests below).
    state = GameState(SpyEffectControls(), SceneControls())
    first = PhaseSlot("shared_machine", _PHASE_A)
    second = PhaseSlot("shared_machine", _PHASE_A)

    assert first(state) is second(state)


# ---------------------------------------------------------------------------
# PhaseRule lifecycle through the engine seam
# ---------------------------------------------------------------------------


def test_on_enter_fires_once_while_the_gated_handler_fires_every_tick() -> None:
    rule = _LifecycleRule(_PHASE_A, "owner")

    names = _run([rule], ticks=3)

    assert names == ["enter:owner", "tick:owner", "tick:owner", "tick:owner"]


def test_on_exit_fires_on_transition_and_the_next_phase_enters() -> None:
    slot = PhaseSlot(_MACHINE_KEY, _PHASE_A)
    leaving = _LifecycleRule(_PHASE_A, "a", phase_slot=slot, transitions_to=_PHASE_B)
    arriving = _LifecycleRule(_PHASE_B, "b", phase_slot=slot)

    names = _run([leaving, arriving], ticks=2)

    # tick1: A enters and ticks, then transitions out (exit on A); because B is
    # registered after A it sees the new phase within the same tick and enters.
    # tick2: only B is active and ticks again.
    assert names == ["enter:a", "tick:a", "exit:a", "enter:b", "tick:b", "tick:b"]


def test_handler_does_not_fire_after_its_phase_is_left() -> None:
    slot = PhaseSlot(_MACHINE_KEY, _PHASE_A)
    leaving = _LifecycleRule(_PHASE_A, "a", phase_slot=slot, transitions_to=_PHASE_B)
    arriving = _LifecycleRule(_PHASE_B, "b", phase_slot=slot)

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
    slot = PhaseSlot(_MACHINE_KEY, _PHASE_A)
    leaving = _LifecycleRule(_PHASE_A, "a", phase_slot=slot, transitions_to=_PHASE_B)
    arriving = _LifecycleRule(_PHASE_B, "b", phase_slot=slot)
    rules = [arriving, leaving] if owner_dispatches_first else [leaving, arriving]

    names = _run(rules, ticks=4)

    assert names.count("enter:b") == 1


# ---------------------------------------------------------------------------
# InPhaseRule — phase-gated, no lifecycle, shareable
# ---------------------------------------------------------------------------


def test_in_phase_rule_handler_fires_only_while_its_phase_is_active() -> None:
    # bystander registered first so it dispatches before the transition each
    # tick: it must not catch the same-tick switch into B on the transition tick.
    slot = PhaseSlot(_MACHINE_KEY, _PHASE_A)
    bystander = _InPhaseEmitter(_PHASE_B, "bystander", phase_slot=slot)
    leaving = _LifecycleRule(_PHASE_A, "a", phase_slot=slot, transitions_to=_PHASE_B)

    names = _run([bystander, leaving], ticks=4)

    # A is active on tick1 only; B is active from tick2 on (3 remaining ticks).
    assert names.count("in:bystander") == 3
    # The bystander never emits while A is the active phase.
    assert names.index("in:bystander") > names.index("tick:a")


def test_in_phase_rule_does_not_consume_the_entry_flag_for_a_phase_owner() -> None:
    # InPhaseRule registered first so it dispatches before the owner each tick;
    # if it consumed the entry flag, the owner's on_enter would never fire.
    slot = PhaseSlot(_MACHINE_KEY, _PHASE_A)
    bystander = _InPhaseEmitter(_PHASE_A, "bystander", phase_slot=slot)
    owner = _LifecycleRule(_PHASE_A, "owner", phase_slot=slot)

    names = _run([bystander, owner], ticks=2)

    assert names.count("enter:owner") == 1


def test_multiple_in_phase_rules_share_one_phase() -> None:
    slot = PhaseSlot(_MACHINE_KEY, _PHASE_A)
    first = _InPhaseEmitter(_PHASE_A, "first", phase_slot=slot)
    second = _InPhaseEmitter(_PHASE_A, "second", phase_slot=slot)

    names = _run([first, second], ticks=1)

    assert "in:first" in names
    assert "in:second" in names


def test_in_phase_rule_and_phase_rule_coexist_on_one_phase() -> None:
    slot = PhaseSlot(_MACHINE_KEY, _PHASE_A)
    owner = _LifecycleRule(_PHASE_A, "owner", phase_slot=slot)
    bystander = _InPhaseEmitter(_PHASE_A, "bystander", phase_slot=slot)

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


def test_same_phase_under_different_phase_slots_loads_cleanly() -> None:
    engine = GameEngine(effect_controls=SpyEffectControls())
    one = _LifecycleRule(_PHASE_A, "one", phase_slot=PhaseSlot("machine_one", _PHASE_A))
    two = _LifecycleRule(_PHASE_A, "two", phase_slot=PhaseSlot("machine_two", _PHASE_A))

    engine.set_rules([one, two])  # does not raise

    assert len(engine.rules) == 2


def test_in_phase_rule_sharing_a_phase_with_its_owner_is_not_a_duplicate() -> None:
    engine = GameEngine(effect_controls=SpyEffectControls())
    slot = PhaseSlot(_MACHINE_KEY, _PHASE_A)
    owner = _LifecycleRule(_PHASE_A, "owner", phase_slot=slot)
    bystander = _InPhaseEmitter(_PHASE_A, "bystander", phase_slot=slot)

    engine.set_rules([owner, bystander])  # does not raise

    assert len(engine.rules) == 2


# ---------------------------------------------------------------------------
# Distinct-PhaseSlot-same-key fail-fast at scene load (GameEngine.set_rules)
# ---------------------------------------------------------------------------


def test_two_distinct_phase_slots_claiming_one_key_fail_at_load_via_two_phase_rules() -> None:
    # Different phases, so the (machine key, phase) dup-owner check alone
    # would not catch this -- only PhaseSlot identity does.
    engine = GameEngine(effect_controls=SpyEffectControls())
    stray_slot = PhaseSlot(_MACHINE_KEY, _PHASE_A)  # distinct instance, same key string
    one = _LifecycleRule(_PHASE_A, "one")  # holds the module-level _DEFAULT_SLOT
    two = _LifecycleRule(_PHASE_B, "two", phase_slot=stray_slot)

    with pytest.raises(ValueError):
        engine.set_rules([one, two])


def test_two_distinct_phase_slots_claiming_one_key_fail_at_load_via_in_phase_rule() -> None:
    # The stray slot is held by an InPhaseRule this time, not a PhaseRule --
    # phase_ownership() alone would never see it, only phase_accessor does.
    engine = GameEngine(effect_controls=SpyEffectControls())
    stray_slot = PhaseSlot(_MACHINE_KEY, _PHASE_A)  # distinct instance, same key string
    owner = _LifecycleRule(_PHASE_A, "owner")  # holds the module-level _DEFAULT_SLOT
    stray = _InPhaseEmitter(_PHASE_B, "stray", phase_slot=stray_slot)

    with pytest.raises(ValueError):
        engine.set_rules([owner, stray])


# ---------------------------------------------------------------------------
# PhaseRule per-instance PhaseSlot — slot identity and phase_ownership
# ---------------------------------------------------------------------------


def test_phase_rule_phase_ownership_returns_slot_key_and_phase() -> None:
    slot = PhaseSlot(_MACHINE_KEY, _PHASE_A)
    rule = _LifecycleRule(_PHASE_A, "owner", phase_slot=slot)

    key, phase = rule.phase_ownership()

    assert key == _MACHINE_KEY
    assert phase is _PHASE_A


def test_shared_phase_slot_resolves_the_same_machine_for_phase_rule_and_in_phase_rule() -> None:
    # A scene constructs exactly one PhaseSlot per machine (e.g. tag_phase) and
    # passes that same instance to every PhaseRule/InPhaseRule plus its own
    # module-level phase reference. All three must resolve the identical
    # cached PhaseMachine.
    slot = PhaseSlot(_MACHINE_KEY, _PHASE_A)
    owner = _LifecycleRule(_PHASE_A, "owner", phase_slot=slot)
    bystander = _InPhaseEmitter(_PHASE_A, "bystander", phase_slot=slot)

    state = GameState(SpyEffectControls(), SceneControls())

    via_module_level_reference = slot(state)
    via_phase_rule = _rule_machine(owner, state)
    via_in_phase_rule = _rule_machine(bystander, state)

    assert via_module_level_reference is via_phase_rule
    assert via_module_level_reference is via_in_phase_rule
