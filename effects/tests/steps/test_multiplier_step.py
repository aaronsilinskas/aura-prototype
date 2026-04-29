import pytest

from effects.effect import Effect, EffectState, EffectTimer
from effects.steps.scale import multiplier


def test_multiplier_applies_start_value_at_beginning_of_duration() -> None:
    # Timer at progress 0.0 → multiplier should equal start (0.25).
    effect = Effect("test", lambda _: 1.0).add_steps([multiplier(0.25, 1.0)])
    state = EffectState()
    timer = EffectTimer(duration=1.0)

    effect.update(state, timer)
    value = effect.value(state, 0.0)

    assert value == pytest.approx(0.25)


def test_multiplier_interpolates_toward_end_value_as_duration_progresses() -> None:
    # Timer at progress 0.5 → multiplier should be midpoint between 0.0 and 1.0.
    effect = Effect("test", lambda _: 1.0).add_steps([multiplier(0.0, 1.0)])
    state = EffectState()
    timer = EffectTimer(duration=1.0)
    timer.update(0.5)

    effect.update(state, timer)
    value = effect.value(state, 0.0)

    assert value == pytest.approx(0.5)


def test_multiplier_is_at_end_value_just_before_duration_completes() -> None:
    # At progress just below 1.0 the step is still active and the multiplier
    # should be very close to the end value. At exactly 1.0 the step clears
    # its state (tested separately below).
    effect = Effect("test", lambda _: 1.0).add_steps([multiplier(0.0, 0.75)])
    state = EffectState()
    timer = EffectTimer(duration=1.0)
    timer.update(0.9999)

    effect.update(state, timer)
    value = effect.value(state, 0.0)

    assert value == pytest.approx(0.75, rel=1e-3)


def test_multiplier_passes_value_through_unchanged_after_duration_completes() -> None:
    # After progress >= 1.0 the step clears its state so adjust_value returns
    # the raw shape value (multiplier of 1.0).  The shape returns 0.7; with a
    # multiplier of 0.0 while active the value would be 0.0, so 0.7 confirms
    # the step is no longer modifying the output.
    effect = Effect("test", lambda _: 0.7).add_steps([multiplier(0.0, 0.0)])
    state = EffectState()
    timer = EffectTimer(duration=1.0)
    timer.update(1.0)

    effect.update(state, timer)
    value = effect.value(state, 0.0)

    assert value == pytest.approx(0.7)
