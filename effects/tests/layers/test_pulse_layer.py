import pytest

from effects.layers.pulse_layer import PulseLayer


def _layer(
    brighten: float = 0.5,
    on: float = 0.5,
    darken: float = 0.5,
    off: float = 0.5,
) -> PulseLayer:
    return PulseLayer(brighten, on, darken, off)


def test_pulse_layer_sample_returns_zero_before_first_update() -> None:
    layer = _layer()
    assert layer.sample(0.0, 10) == pytest.approx(0.0)


def test_pulse_layer_brighten_phase_interpolates_brightness_linearly() -> None:
    layer = _layer(brighten=0.5)
    layer.update(0.25)  # t = 0.5 → brightness = 0.5
    assert layer.sample(0.0, 10) == pytest.approx(0.5)


def test_pulse_layer_at_end_of_brighten_returns_full_brightness() -> None:
    layer = _layer(brighten=0.5)
    layer.update(0.5)
    assert layer.sample(0.0, 10) == pytest.approx(1.0)


def test_pulse_layer_on_phase_holds_full_brightness() -> None:
    layer = _layer(brighten=0.5, on=0.5)
    layer.update(0.75)  # mid-ON
    assert layer.sample(0.0, 10) == pytest.approx(1.0)


def test_pulse_layer_darken_phase_interpolates_brightness_back_to_zero() -> None:
    layer = _layer(brighten=0.5, on=0.5, darken=0.5)
    layer.update(1.25)  # mid-darken → t = 0.5 → brightness = 0.5
    assert layer.sample(0.0, 10) == pytest.approx(0.5)


def test_pulse_layer_off_phase_returns_zero_brightness() -> None:
    layer = _layer(brighten=0.5, on=0.5, darken=0.5, off=0.5)
    layer.update(1.75)  # mid-OFF
    assert layer.sample(0.0, 10) == pytest.approx(0.0)


def test_pulse_layer_update_wraps_after_full_cycle() -> None:
    layer_a = _layer()
    layer_a.update(0.25)

    layer_b = _layer()
    layer_b.update(2.25)  # full cycle (2.0) + 0.25

    assert layer_a.sample(0.0, 10) == pytest.approx(layer_b.sample(0.0, 10))


def test_pulse_layer_darken_brightness_is_correct_when_off_duration_is_zero() -> None:
    layer = _layer(brighten=0.5, on=0.5, darken=0.5, off=0.0)
    # cycle = 1.5 s; at t=1.4 (near end of DARKEN): t=(1.4-1.0)/0.5=0.8 → brightness=0.2
    layer.update(1.4)
    assert layer.sample(0.0, 10) == pytest.approx(0.2)


@pytest.mark.parametrize(
    ("elapsed", "brightness"),
    [
        (0.1, 0.5),  # halfway through brighten (0.2 s)
        (0.5, 1.0),  # on, which ends 0.6 s in
        (0.75, 0.5),  # halfway through darken (0.6 s to 0.9 s)
        (0.95, 0.0),  # off, the last 0.1 s of the 1.0 s cycle
        (1.1, 0.5),  # halfway through the next cycle's brighten
    ],
)
def test_pulse_layer_phases_follow_their_own_durations(elapsed: float, brightness: float) -> None:
    layer = _layer(brighten=0.2, on=0.4, darken=0.3, off=0.1)
    layer.update(elapsed)
    assert layer.sample(0.0, 10) == pytest.approx(brightness)


def test_pulse_layer_update_with_zero_elapsed_does_not_advance_phase() -> None:
    layer = _layer(brighten=0.5)
    layer.update(0.0)
    assert layer.sample(0.0, 10) == pytest.approx(0.0)


def test_pulse_layer_sample_returns_same_value_for_all_positions() -> None:
    layer = _layer()
    layer.update(0.25)
    assert layer.sample(0.0, 10) == pytest.approx(layer.sample(0.5, 10))
    assert layer.sample(0.0, 10) == pytest.approx(layer.sample(0.99, 10))


@pytest.mark.parametrize(
    ("brighten", "on", "darken", "off"),
    [
        (-0.1, 0.5, 0.5, 0.5),
        (0.5, -0.1, 0.5, 0.5),
        (0.5, 0.5, -0.1, 0.5),
        (0.5, 0.5, 0.5, -0.1),
    ],
)
def test_pulse_layer_rejects_a_negative_duration(
    brighten: float, on: float, darken: float, off: float
) -> None:
    with pytest.raises(ValueError):
        PulseLayer(brighten, on, darken, off)


def test_pulse_layer_rejects_an_all_zero_cycle() -> None:
    with pytest.raises(ValueError):
        PulseLayer(0.0, 0.0, 0.0, 0.0)
