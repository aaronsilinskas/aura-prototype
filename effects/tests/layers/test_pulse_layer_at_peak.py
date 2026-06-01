"""Tests for PulseLayer.at_peak flag and raw _elapsed accumulator."""

import pytest

from effects.layers.pulse_layer import PulseLayer


def _layer(
    b_on: float = 0.5,
    on_dur: float = 0.5,
    darken_dur: float = 0.5,
    off_dur: float = 0.5,
) -> PulseLayer:
    b_darken = b_on + on_dur
    b_off = b_darken + darken_dur
    cycle_total = b_off + off_dur
    return PulseLayer(b_on, b_darken, b_off, cycle_total)


# --- at_peak in __slots__ and initialized False ---


def test_pulse_layer_at_peak_initialized_false() -> None:
    layer = _layer()
    assert layer.at_peak is False


# --- at_peak is False before reaching b_on ---


def test_pulse_layer_at_peak_false_during_brighten() -> None:
    layer = _layer(b_on=0.5)
    layer.update(0.3)
    assert layer.at_peak is False


# --- at_peak is True on the exact tick that crosses b_on ---


def test_pulse_layer_at_peak_true_when_elapsed_crosses_b_on() -> None:
    layer = _layer(b_on=0.5)
    layer.update(0.6)  # crosses b_on=0.5
    assert layer.at_peak is True


# --- at_peak is True when elapsed exactly equals b_on ---


def test_pulse_layer_at_peak_true_when_elapsed_equals_b_on_exactly() -> None:
    layer = _layer(b_on=0.5)
    layer.update(0.5)
    assert layer.at_peak is True


# --- at_peak is False during ON phase after the crossing tick ---


def test_pulse_layer_at_peak_false_during_on_phase_after_crossing() -> None:
    layer = _layer(b_on=0.5, on_dur=0.5)
    layer.update(0.5)  # peak tick
    layer.update(0.2)  # still in ON, no new crossing
    assert layer.at_peak is False


# --- at_peak is False during darken phase ---


def test_pulse_layer_at_peak_false_during_darken() -> None:
    layer = _layer(b_on=0.5, on_dur=0.5, darken_dur=0.5)
    layer.update(0.6)  # cross b_on → at_peak=True
    layer.update(0.8)  # into darken, no b_on crossing → at_peak=False
    assert layer.at_peak is False


# --- at_peak is False during off phase ---


def test_pulse_layer_at_peak_false_during_off() -> None:
    layer = _layer(b_on=0.5, on_dur=0.5, darken_dur=0.5, off_dur=0.5)
    layer.update(0.6)  # cross b_on
    layer.update(1.15)  # into off phase, no new crossing
    assert layer.at_peak is False


def test_pulse_layer_at_peak_true_on_second_cycle_crossing() -> None:
    layer = _layer(b_on=0.5, on_dur=0.5, darken_dur=0.5, off_dur=0.5)
    # Advance through first cycle and into second cycle's brighten-to-ON crossing
    layer.update(2.0)  # t=2.0 (start of cycle 2)
    layer.update(0.6)  # t=2.6, crosses b_on in cycle 2 (2.0 + 0.5 = 2.5)
    assert layer.at_peak is True


# --- Interval detection: large elapsed skips over peak ---


def test_pulse_layer_at_peak_true_when_large_elapsed_skips_past_peak() -> None:
    # Start at 0.0, one large update that skips from before b_on to after b_on
    layer = _layer(b_on=0.5, on_dur=0.5, darken_dur=0.5, off_dur=0.5)
    layer.update(1.8)  # jumps from 0 to 1.8; crosses b_on=0.5 in first interval
    assert layer.at_peak is True


def test_pulse_layer_at_peak_true_when_large_elapsed_skips_entire_cycle() -> None:
    # A single update large enough to cover more than a full cycle still detects at_peak
    layer = _layer(b_on=0.5, on_dur=0.5, darken_dur=0.5, off_dur=0.5)
    layer.update(3.0)  # crosses at least one b_on boundary
    assert layer.at_peak is True


# --- sample() still uses modulo internally for visual correctness ---


def test_pulse_layer_sample_correct_after_more_than_one_cycle() -> None:
    # After 2.0 s (one full cycle), elapsed=0.0 visually → start brightness=0.0
    layer_a = _layer()
    layer_a.update(0.25)

    layer_b = _layer()
    layer_b.update(2.25)  # full cycle (2.0) + 0.25

    assert layer_a.sample(0.0, 10) == pytest.approx(layer_b.sample(0.0, 10))
