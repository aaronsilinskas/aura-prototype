"""Behaviour-driven tests for ``IrRangeReceiverRule`` -- the scene-local rule
that renders IR reception quality as a green/yellow/red pixel meter.

Mirrors the tag/red_light_green_light rule-test pattern: a recording
``SpyEffectControls`` plus fabricated ``NetworkEvents.IRReceived`` and
``InputEvents.Sensors`` events dispatched through a real ``GameEngine``.
"""

from __future__ import annotations

import pytest

from engine.engine import GameEngine
from engine.input import ButtonData, InputEvents
from engine.network import NetworkEvents
from engine.state import GameState, SceneControls, Scope
from engine.tests.helpers import SpyEffectControls
from packs.scenes.ir_range_receiver.rules.helpers.reception_quality_meter import (
    COLOR_GREEN,
    COLOR_RED,
    COLOR_YELLOW,
)
from packs.scenes.ir_range_receiver.rules.receiver_rule import IrRangeReceiverRule


class _StubTimer:
    def __init__(self) -> None:
        self.elapsed: float = 0.0
        self.total: float = 0.0

    def update(self) -> None:
        pass


@pytest.fixture()
def spy() -> SpyEffectControls:
    return SpyEffectControls()


def _make_state(spy: SpyEffectControls, initial_data: dict | None = None):
    timer = _StubTimer()
    engine = GameEngine(spy, timer=timer)  # pyright: ignore[reportArgumentType]
    engine.add_rules(IrRangeReceiverRule())
    state = engine.create_state(SceneControls(), initial_data=initial_data or {})
    return state, engine, timer


def _sensors_event() -> InputEvents.Sensors:
    return InputEvents.Sensors(ButtonData(states={}))


def _ir_event(sequence: int, best_receiver: str = "rx0") -> NetworkEvents.IRReceived:
    return NetworkEvents.IRReceived(
        data=bytes([sequence]),
        signal_strength=1.0,
        error_margin=0,
        best_receiver=best_receiver,
    )


def _tick(
    state: GameState, engine: GameEngine, timer: _StubTimer, total: float, ir_events=()
) -> None:
    timer.total = total
    for event in ir_events:
        state.queue_event(event)
    state.queue_event(_sensors_event())
    engine.update(state)


def test_first_tick_with_no_packets_ever_paints_solid_red(spy):
    state, engine, timer = _make_state(spy)

    _tick(state, engine, timer, total=0.0)

    assert len(spy.set_effect_calls) == 1
    scope, name, opts = spy.set_effect_calls[0]
    assert scope is Scope.NON_AMBIENT
    assert name == "basic.solid"
    assert opts["color"] == COLOR_RED


def test_clean_packet_stream_paints_solid_green(spy):
    state, engine, timer = _make_state(spy)

    _tick(state, engine, timer, total=0.0, ir_events=[_ir_event(0)])
    _tick(state, engine, timer, total=0.1, ir_events=[_ir_event(1)])

    scope, name, opts = spy.set_effect_calls[-1]
    assert scope is Scope.NON_AMBIENT
    assert name == "basic.solid"
    assert opts["color"] == COLOR_GREEN


def test_state_unchanged_between_ticks_does_not_reissue_the_effect(spy):
    state, engine, timer = _make_state(spy)
    _tick(state, engine, timer, total=0.0, ir_events=[_ir_event(0)])
    spy.set_effect_calls.clear()

    _tick(state, engine, timer, total=0.1, ir_events=[_ir_event(1)])  # still Perfect

    assert spy.set_effect_calls == []


def test_gap_in_the_stream_paints_a_progress_bar_at_the_reception_fraction(spy):
    state, engine, timer = _make_state(spy)
    _tick(state, engine, timer, total=0.0, ir_events=[_ir_event(0)])
    spy.set_effect_calls.clear()

    _tick(state, engine, timer, total=0.1, ir_events=[_ir_event(5)])  # gap of 5 -- 4 dropped

    assert len(spy.set_effect_calls) == 1
    scope, name, opts = spy.set_effect_calls[0]
    assert scope is Scope.NON_AMBIENT
    assert name == "basic.progress"
    assert opts["color"] == COLOR_YELLOW
    assert opts["progress"] == pytest.approx(2 / 6)


def test_progress_bar_updates_as_the_rate_moves_while_still_partial(spy):
    """basic.progress bakes its fill in at construction -- if the rule only
    re-issued on a categorical state change, the bar would freeze at whatever
    rate first entered Partial. The rate must keep re-issuing here even though
    the state label ("partial") never changes."""
    state, engine, timer = _make_state(spy)
    _tick(state, engine, timer, total=0.0, ir_events=[_ir_event(0)])
    _tick(state, engine, timer, total=0.1, ir_events=[_ir_event(5)])  # gap of 5 -- Partial
    spy.set_effect_calls.clear()

    _tick(state, engine, timer, total=0.2, ir_events=[_ir_event(6)])  # contiguous -- rate rises

    assert len(spy.set_effect_calls) == 1
    scope, name, opts = spy.set_effect_calls[0]
    assert scope is Scope.NON_AMBIENT
    assert name == "basic.progress"
    assert opts["progress"] == pytest.approx(3 / 7)


def test_silence_past_the_timeout_after_packets_reverts_to_solid_red(spy):
    state, engine, timer = _make_state(spy)
    _tick(state, engine, timer, total=0.0, ir_events=[_ir_event(0)])
    spy.set_effect_calls.clear()

    _tick(state, engine, timer, total=0.6)  # 0.6s since the last packet, timeout is 0.5s

    assert len(spy.set_effect_calls) == 1
    scope, name, opts = spy.set_effect_calls[0]
    assert scope is Scope.NON_AMBIENT
    assert name == "basic.solid"
    assert opts["color"] == COLOR_RED


def test_reception_is_unaffected_by_which_receiver_reported_the_packet(spy):
    """An IR multi-receiver (aura-device.json declaring 2+ rx pins) surfaces
    the best-margin receiver per packet -- best_receiver varies freely and
    must not affect reception-quality classification."""
    state, engine, timer = _make_state(spy)

    _tick(state, engine, timer, total=0.0, ir_events=[_ir_event(0, best_receiver="rx0")])
    _tick(state, engine, timer, total=0.1, ir_events=[_ir_event(1, best_receiver="rx1")])

    _scope, name, opts = spy.set_effect_calls[-1]
    assert name == "basic.solid"
    assert opts["color"] == COLOR_GREEN


def test_prints_a_periodic_serial_line_with_state_and_counts(spy, capsys):
    state, engine, timer = _make_state(spy)

    _tick(state, engine, timer, total=0.0, ir_events=[_ir_event(0)])

    output = capsys.readouterr().out
    assert "[ir_range" in output
    assert "state=perfect" in output
    assert "received=1" in output
    assert "dropped=0" in output


def test_print_is_rate_limited_and_does_not_print_every_tick(spy, capsys):
    state, engine, timer = _make_state(spy)
    _tick(state, engine, timer, total=0.0, ir_events=[_ir_event(0)])
    capsys.readouterr()  # discard the first tick's print

    _tick(state, engine, timer, total=0.1, ir_events=[_ir_event(1)])

    assert capsys.readouterr().out == ""
