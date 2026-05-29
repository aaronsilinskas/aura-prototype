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


# --- BRIGHTEN phase ---


def test_pulse_layer_sample_returns_zero_before_first_update() -> None:
    layer = _layer()
    assert layer.sample(0.0, 10) == pytest.approx(0.0)


def test_pulse_layer_brighten_phase_interpolates_brightness_linearly() -> None:
    layer = _layer(b_on=0.5)
    layer.update(0.25)  # t = 0.5 → brightness = 0.5
    assert layer.sample(0.0, 10) == pytest.approx(0.5)


def test_pulse_layer_at_b_on_boundary_returns_full_brightness() -> None:
    layer = _layer(b_on=0.5)
    layer.update(0.5)
    assert layer.sample(0.0, 10) == pytest.approx(1.0)


# --- ON phase ---


def test_pulse_layer_on_phase_holds_full_brightness() -> None:
    layer = _layer(b_on=0.5, on_dur=0.5)
    layer.update(0.75)  # mid-ON
    assert layer.sample(0.0, 10) == pytest.approx(1.0)


# --- DARKEN phase ---


def test_pulse_layer_darken_phase_interpolates_brightness_back_to_zero() -> None:
    layer = _layer(b_on=0.5, on_dur=0.5, darken_dur=0.5)
    layer.update(1.25)  # mid-darken → t = 0.5 → brightness = 0.5
    assert layer.sample(0.0, 10) == pytest.approx(0.5)


# --- OFF phase ---


def test_pulse_layer_off_phase_returns_zero_brightness() -> None:
    layer = _layer(b_on=0.5, on_dur=0.5, darken_dur=0.5, off_dur=0.5)
    layer.update(1.75)  # mid-OFF
    assert layer.sample(0.0, 10) == pytest.approx(0.0)


# --- Wrap ---


def test_pulse_layer_update_wraps_after_full_cycle() -> None:
    layer_a = _layer()
    layer_a.update(0.25)

    layer_b = _layer()
    layer_b.update(2.25)  # full cycle (2.0) + 0.25

    assert layer_a.sample(0.0, 10) == pytest.approx(layer_b.sample(0.0, 10))


# --- off_duration = 0 ---


def test_pulse_layer_darken_brightness_is_correct_when_off_duration_is_zero() -> None:
    layer = _layer(b_on=0.5, on_dur=0.5, darken_dur=0.5, off_dur=0.0)
    # cycle_total = 1.5; at t=1.4 (near end of DARKEN): t=(1.4-1.0)/0.5=0.8 → brightness=0.2
    layer.update(1.4)
    assert layer.sample(0.0, 10) == pytest.approx(0.2)


# --- Position independence ---


def test_pulse_layer_update_with_zero_elapsed_does_not_advance_phase() -> None:
    layer = _layer(b_on=0.5)
    layer.update(0.0)
    assert layer.sample(0.0, 10) == pytest.approx(0.0)


def test_pulse_layer_sample_returns_same_value_for_all_positions() -> None:
    layer = _layer()
    layer.update(0.25)
    assert layer.sample(0.0, 10) == pytest.approx(layer.sample(0.5, 10))
    assert layer.sample(0.0, 10) == pytest.approx(layer.sample(0.99, 10))
