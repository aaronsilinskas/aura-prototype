import pytest

from effects.effect import Effect, EffectState
from effects.steps.drift_noise import drift_noise
from effects.tests.helpers import make_timer


def test_drift_noise_with_zero_amplitude_is_a_passthrough() -> None:
    effect = Effect("test", lambda _: 0.5).add_steps([drift_noise(amplitude=0.0)])
    state = EffectState()

    effect.update(state, make_timer(0.1))
    value = effect.value(state, 0.0, 1)

    assert value == pytest.approx(0.5)


def test_drift_noise_does_not_decrease_value_below_input() -> None:
    # Noise buffer values are always in [0, 1], so additive blending can only increase.
    effect = Effect("test", lambda _: 0.3).add_steps([drift_noise(amplitude=0.4)])
    state = EffectState()

    effect.update(state, make_timer(0.1))

    for pos in [0.0, 0.25, 0.5, 0.75]:
        assert effect.value(state, pos, 1) >= 0.3


def test_drift_noise_with_zero_drift_speed_reads_same_noise_value_each_frame() -> None:
    # With no drift, the noise buffer offset never moves, so position 0 always
    # samples the same buffer entry regardless of how many frames have passed.
    effect = Effect("test", lambda _: 0.0).add_steps([drift_noise(drift_speed=0.0, amplitude=1.0)])
    state = EffectState()

    effect.update(state, make_timer(0.1))
    value_frame1 = effect.value(state, 0.0, 1)
    effect.update(state, make_timer(0.1))
    value_frame2 = effect.value(state, 0.0, 1)

    assert value_frame1 == pytest.approx(value_frame2)


def test_drift_noise_with_positive_drift_speed_shifts_the_sampled_position_over_time() -> None:
    # With resolution=10, drift_speed=1.0, elapsed=0.1: buffer offset advances by exactly
    # 1 slot per frame. position=0.1 maps to index 1.0 (0.1 * 10) when buffer offset=0.
    # After one drift frame, position=0.0 maps to the same index (0.0 * 10 + 1.0 = 1.0).
    effect = Effect("test", lambda _: 0.0).add_steps(
        [drift_noise(resolution=10, drift_speed=1.0, amplitude=1.0)]
    )
    state = EffectState()

    effect.update(state, make_timer(0.0))  # initialize buffer, buffer offset stays at 0
    value_before_drift = effect.value(state, 0.1, 1)  # position 0.1 → index 1.0 → noise[1]

    effect.update(state, make_timer(0.1))  # buffer offset advances to 1.0
    value_after_drift = effect.value(state, 0.0, 1)  # position 0.0 → index 0.0 + 1.0 → noise[1]

    assert value_after_drift == pytest.approx(value_before_drift)


def test_drift_noise_produces_distinct_values_as_buffer_offset_advances() -> None:
    # With drift_speed=1.0, resolution=10, elapsed=0.1: each frame shifts the offset
    # by 1 slot, drawing from a different random buffer entry each time. Over 5 frames
    # the sampled values at position 0 should not all be identical.
    effect = Effect("test", lambda _: 0.0).add_steps(
        [drift_noise(resolution=10, drift_speed=1.0, amplitude=1.0)]
    )
    state = EffectState()

    samples = []
    for _ in range(5):
        effect.update(state, make_timer(0.1))
        samples.append(effect.value(state, 0.0, 1))

    assert len(set(samples)) > 1
