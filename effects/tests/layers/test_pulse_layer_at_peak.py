import pytest

from effects.layers.pulse_layer import PulseLayer


def _layer(
    brighten: float = 0.5,
    on: float = 0.5,
    darken: float = 0.5,
    off: float = 0.5,
) -> PulseLayer:
    return PulseLayer(brighten, on, darken, off)


def test_pulse_layer_at_peak_initialized_false() -> None:
    layer = _layer()
    assert layer.at_peak is False


def test_pulse_layer_at_peak_false_during_brighten() -> None:
    layer = _layer(brighten=0.5)
    layer.update(0.3)
    assert layer.at_peak is False


def test_pulse_layer_at_peak_true_when_elapsed_crosses_end_of_brighten() -> None:
    layer = _layer(brighten=0.5)
    layer.update(0.6)  # crosses the end of brighten at 0.5
    assert layer.at_peak is True


def test_pulse_layer_at_peak_true_when_elapsed_equals_end_of_brighten_exactly() -> None:
    layer = _layer(brighten=0.5)
    layer.update(0.5)
    assert layer.at_peak is True


def test_pulse_layer_at_peak_false_during_on_phase_after_crossing() -> None:
    layer = _layer(brighten=0.5, on=0.5)
    layer.update(0.5)  # peak tick
    layer.update(0.2)  # still in ON, no new crossing
    assert layer.at_peak is False


def test_pulse_layer_at_peak_false_during_darken() -> None:
    layer = _layer(brighten=0.5, on=0.5, darken=0.5)
    layer.update(0.6)  # cross the end of brighten → at_peak=True
    layer.update(0.8)  # into darken, no crossing → at_peak=False
    assert layer.at_peak is False


def test_pulse_layer_at_peak_false_during_off() -> None:
    layer = _layer(brighten=0.5, on=0.5, darken=0.5, off=0.5)
    layer.update(0.6)  # cross the end of brighten
    layer.update(1.15)  # into off phase, no new crossing
    assert layer.at_peak is False


def test_pulse_layer_at_peak_true_on_second_cycle_crossing() -> None:
    layer = _layer(brighten=0.5, on=0.5, darken=0.5, off=0.5)
    # Advance through first cycle and into second cycle's brighten-to-ON crossing
    layer.update(2.0)  # t=2.0 (start of cycle 2)
    layer.update(0.6)  # t=2.6, crosses the end of brighten in cycle 2 (2.0 + 0.5 = 2.5)
    assert layer.at_peak is True


def test_pulse_layer_at_peak_true_when_large_elapsed_skips_past_peak() -> None:
    # Start at 0.0, one large update that skips past the end of brighten
    layer = _layer(brighten=0.5, on=0.5, darken=0.5, off=0.5)
    layer.update(1.8)  # jumps from 0 to 1.8; crosses the end of brighten at 0.5 in first interval
    assert layer.at_peak is True


def test_pulse_layer_at_peak_true_when_large_elapsed_skips_entire_cycle() -> None:
    # A single update large enough to cover more than a full cycle still detects at_peak
    layer = _layer(brighten=0.5, on=0.5, darken=0.5, off=0.5)
    layer.update(3.0)  # crosses at least one end of brighten
    assert layer.at_peak is True


def test_pulse_layer_at_peak_true_only_on_the_tick_that_ends_brighten() -> None:
    layer = _layer(brighten=0.25, on=0.5, darken=0.125, off=0.125)
    peaks = []
    for _ in range(16):  # two 1.0 s cycles in 0.125 s ticks
        layer.update(0.125)
        peaks.append(layer.at_peak)
    assert [i for i, peak in enumerate(peaks) if peak] == [1, 9]


def test_pulse_layer_sample_correct_after_more_than_one_cycle() -> None:
    # After 2.0 s (one full cycle), elapsed=0.0 visually → start brightness=0.0
    layer_a = _layer()
    layer_a.update(0.25)

    layer_b = _layer()
    layer_b.update(2.25)  # full cycle (2.0) + 0.25

    assert layer_a.sample(0.0, 10) == pytest.approx(layer_b.sample(0.0, 10))
