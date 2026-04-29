import pytest
from effects.tests.helpers import (
    AlwaysAdvance,
    MultiplyValue,
    NeverAdvance,
    OffsetPosition,
    RecordAndHold,
    make_timer,
)

from effects.effect import Effect, EffectState, EffectStep, EffectTimer

# ---------------------------------------------------------------------------
# Effect construction
# ---------------------------------------------------------------------------


def test_add_steps_returns_effect_for_fluent_chaining() -> None:
    effect = Effect("test")

    result = effect.add_steps([NeverAdvance()])

    assert result is effect


# ---------------------------------------------------------------------------
# Effect.value — sampling guarantees
# ---------------------------------------------------------------------------


def test_effect_with_no_steps_samples_shape_directly() -> None:
    effect = Effect("test", lambda _: 0.75)
    state = EffectState()

    value = effect.value(state, 0.0)

    assert value == 0.75


def test_effect_applies_position_offset_before_sampling_shape() -> None:
    # Shape returns the raw position, so we can verify what position was passed in.
    effect = Effect("test", lambda pos: pos).add_steps([OffsetPosition(0.25)])
    state = EffectState()
    effect.update(state, make_timer(0.016))

    value = effect.value(state, 0.5)

    # Position 0.5 + 0.25 offset = 0.75 wrapped into [0,1], shape returns it directly.
    assert value == pytest.approx(0.75)


def test_effect_applies_value_transforms_in_step_order() -> None:
    # Two multiplier steps: first halves (×0.5), then doubles (×2.0).
    # Net result should be the original shape value (×1.0).
    effect = Effect("test", lambda _: 0.6).add_steps(
        [MultiplyValue(0.5), MultiplyValue(2.0)]
    )
    state = EffectState()
    effect.update(state, make_timer(0.016))

    value = effect.value(state, 0.0)

    assert value == pytest.approx(0.6)


def test_effect_clamps_output_above_one_when_step_amplifies_value() -> None:
    effect = Effect("test", lambda _: 0.8).add_steps([MultiplyValue(3.0)])
    state = EffectState()
    effect.update(state, make_timer(0.016))

    value = effect.value(state, 0.0)

    assert value == 1.0


def test_effect_clamps_output_below_zero_when_step_inverts_value() -> None:
    effect = Effect("test", lambda _: 0.5).add_steps([MultiplyValue(-2.0)])
    state = EffectState()
    effect.update(state, make_timer(0.016))

    value = effect.value(state, 0.0)

    assert value == 0.0


# ---------------------------------------------------------------------------
# Effect.update — step sequencing guarantees
# ---------------------------------------------------------------------------


def test_effect_advances_to_next_step_when_current_step_completes() -> None:
    log: list = []
    effect = Effect("test").add_steps(
        [
            AlwaysAdvance(),
            RecordAndHold("second", log),
        ]
    )
    state = EffectState()

    effect.update(state, make_timer(0.016))

    assert log == ["second"]


def test_effect_stays_on_active_step_across_frames_when_step_holds() -> None:
    log: list = []
    effect = Effect("test").add_steps(
        [
            RecordAndHold("first", log),
            RecordAndHold("second", log),
        ]
    )
    state = EffectState()
    timer = make_timer(0.016)

    effect.update(state, timer)
    effect.update(state, timer)

    assert log == ["first", "first"]


def test_effect_can_advance_through_multiple_steps_in_one_frame() -> None:
    log: list = []
    effect = Effect("test").add_steps(
        [
            AlwaysAdvance(),
            AlwaysAdvance(),
            RecordAndHold("third", log),
        ]
    )
    state = EffectState()

    effect.update(state, make_timer(0.016))

    assert log == ["third"]


def test_effect_wraps_back_to_first_step_after_last_step_advances() -> None:
    # Seed the state at the last step; after it advances the sequence should
    # wrap and the first step should fire within the same frame.
    log: list = []
    effect = Effect("test").add_steps(
        [
            RecordAndHold("first", log),
            AlwaysAdvance(),
        ]
    )
    state = EffectState()
    state.set_step_index(effect, 1)  # start at last step

    effect.update(state, make_timer(0.016))

    assert log == ["first"]


# ---------------------------------------------------------------------------
# EffectState isolation guarantees
# ---------------------------------------------------------------------------


def test_two_states_drive_same_effect_independently() -> None:
    log: list = []

    class _AdvanceOnce(EffectStep):
        """Advances once on the first update, then stays active indefinitely."""

        def update(self, state: EffectState, timer: EffectTimer) -> bool:
            if state.get_step_data(self, bool) is None:
                state.set_step_data(self, True)
                return True
            return False

    advance_step = _AdvanceOnce()
    record_step = RecordAndHold("second", log)
    effect = Effect("test").add_steps([advance_step, record_step])

    state_a = EffectState()
    state_b = EffectState()
    timer = make_timer(0.016)

    # Advance state_a past the first step.
    effect.update(state_a, timer)
    # state_b has not been updated — first update should advance it too, independently.
    effect.update(state_b, timer)

    # Both states should have reached the second step: log has two entries.
    assert log == ["second", "second"]
