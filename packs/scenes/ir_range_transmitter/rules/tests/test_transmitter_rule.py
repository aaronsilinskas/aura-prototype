"""Tests for ``IrRangeTransmitterRule`` — fixed-rate, sequence-numbered IR sends."""

from __future__ import annotations

from engine.engine import GameEngine
from engine.input import ButtonData, InputEvents
from engine.network import LINE
from engine.state import GameState, SceneControls
from engine.tests.helpers import SpyEffectControls, SpyNetworkControls
from packs.scenes.ir_range_transmitter.rules.transmitter_rule import IrRangeTransmitterRule


class _StubTimer:
    """Controllable timer for tests that need specific ``state.total`` values."""

    def __init__(self) -> None:
        self.elapsed: float = 0.0
        self.total: float = 0.0

    def update(self) -> None:
        pass  # Caller controls total directly


def _make_state(
    initial_data: dict | None = None,
) -> tuple[GameState, GameEngine, _StubTimer, SpyNetworkControls]:
    network_spy = SpyNetworkControls()
    timer = _StubTimer()
    engine = GameEngine(SpyEffectControls(), network_controls=network_spy, timer=timer)  # pyright: ignore[reportArgumentType]
    engine.add_rules(IrRangeTransmitterRule())
    state = engine.create_state(SceneControls(), initial_data=initial_data or {})
    return state, engine, timer, network_spy


def _tick(state: GameState, engine: GameEngine, timer: _StubTimer, total: float) -> None:
    timer.total = total
    state.queue_event(InputEvents.Sensors(ButtonData(states={})))
    engine.update(state)


# ---------------------------------------------------------------------------
# Auto-start on boot
# ---------------------------------------------------------------------------


def test_first_tick_sends_immediately_with_no_prior_send():
    state, engine, timer, network_spy = _make_state()

    _tick(state, engine, timer, 0.0)

    assert len(network_spy.send_ir_calls) == 1
    _, emitter = network_spy.send_ir_calls[0]
    assert emitter == LINE


# ---------------------------------------------------------------------------
# Time-gating on state.total
# ---------------------------------------------------------------------------


def test_ticks_within_the_send_period_send_nothing_more():
    state, engine, timer, network_spy = _make_state(initial_data={"irtx_send_rate_hz": 5.0})

    _tick(state, engine, timer, 0.0)
    _tick(state, engine, timer, 0.1)  # 0.1s < 0.2s period -- still gated

    assert len(network_spy.send_ir_calls) == 1


def test_first_tick_past_the_send_period_sends_again():
    state, engine, timer, network_spy = _make_state(initial_data={"irtx_send_rate_hz": 5.0})

    _tick(state, engine, timer, 0.0)
    _tick(state, engine, timer, 0.1)  # gated
    _tick(state, engine, timer, 0.2)  # 0.2s elapsed -- period has elapsed

    assert len(network_spy.send_ir_calls) == 2


# ---------------------------------------------------------------------------
# Sequence byte
# ---------------------------------------------------------------------------


def test_first_send_carries_sequence_zero_in_byte_zero():
    state, engine, timer, network_spy = _make_state()

    _tick(state, engine, timer, 0.0)

    payload, _ = network_spy.send_ir_calls[0]
    assert payload[0] == 0


def test_successive_sends_carry_incrementing_sequence_numbers():
    state, engine, timer, network_spy = _make_state(initial_data={"irtx_send_rate_hz": 5.0})

    _tick(state, engine, timer, 0.0)
    _tick(state, engine, timer, 0.2)
    _tick(state, engine, timer, 0.4)

    sequences = [payload[0] for payload, _ in network_spy.send_ir_calls]
    assert sequences == [0, 1, 2]


def test_sequence_byte_wraps_from_255_back_to_zero():
    # A send rate far above the tick rate so every tick's total comfortably
    # clears the send period, with no floating-point boundary flakiness.
    state, engine, timer, network_spy = _make_state(initial_data={"irtx_send_rate_hz": 1_000_000.0})

    for i in range(257):
        _tick(state, engine, timer, i * 1.0)

    sequences = [payload[0] for payload, _ in network_spy.send_ir_calls]
    assert sequences[254:257] == [254, 255, 0]


# ---------------------------------------------------------------------------
# Payload padding marker
# ---------------------------------------------------------------------------


def test_send_payload_padding_carries_the_fixed_non_zero_marker():
    state, engine, timer, network_spy = _make_state(initial_data={"irtx_payload_size": 4})

    _tick(state, engine, timer, 0.0)

    payload, _ = network_spy.send_ir_calls[0]
    assert bytes(payload[1:]) == bytes([0xA1, 0xA2, 0xA3])
