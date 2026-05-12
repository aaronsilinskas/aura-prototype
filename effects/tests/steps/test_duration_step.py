import pytest

from effects.effect import Effect, EffectState
from effects.steps.duration import duration
from effects.tests.helpers import (
    CountUpdates,
    MultiplyValue,
    OffsetPosition,
    RecordAndHold,
    make_timer,
)

# ---------------------------------------------------------------------------
# Child step transforms — active while timer is running
# ---------------------------------------------------------------------------


def test_duration_step_applies_child_position_transform_while_active() -> None:
    # Shape returns the raw position; with a +0.25 offset the output should shift.
    effect = Effect("test", lambda pos: pos % 1.0).add_steps(
        [duration(1.0, steps=[OffsetPosition(0.25)])]
    )
    state = EffectState()

    effect.update(state, make_timer(0.1))
    value = effect.value(state, 0.5, 1)

    assert value == pytest.approx(0.75)


def test_duration_step_applies_child_value_transform_while_active() -> None:
    effect = Effect("test", lambda _: 0.8).add_steps([duration(1.0, steps=[MultiplyValue(0.5)])])
    state = EffectState()

    effect.update(state, make_timer(0.1))
    value = effect.value(state, 0.0, 1)

    assert abs(value - 0.4) < 1e-6


def test_duration_step_does_not_apply_child_transforms_before_first_update() -> None:
    # Value transforms should not be active before any update has been called.
    effect = Effect("test", lambda _: 0.8).add_steps([duration(1.0, steps=[MultiplyValue(0.0)])])
    state = EffectState()

    value = effect.value(state, 0.0, 1)

    assert value == pytest.approx(0.8)


# ---------------------------------------------------------------------------
# Advancement — expiry triggers the next parent step
# ---------------------------------------------------------------------------


def test_duration_step_advances_to_next_parent_step_when_time_expires() -> None:
    log: list = []
    effect = Effect("test").add_steps(
        [
            duration(0.5),
            RecordAndHold("next", log),
        ]
    )
    state = EffectState()

    effect.update(state, make_timer(1.0))  # far exceeds the 0.5s duration

    assert log == ["next"]


def test_duration_step_does_not_advance_before_duration_expires() -> None:
    log: list = []
    effect = Effect("test").add_steps(
        [
            duration(1.0),
            RecordAndHold("next", log),
        ]
    )
    state = EffectState()

    effect.update(state, make_timer(0.4))

    assert log == []


# ---------------------------------------------------------------------------
# persist_steps=False — child state is cleared on expiry
# ---------------------------------------------------------------------------


def test_duration_step_clears_child_transforms_after_expiry_by_default() -> None:
    # After duration expires, value transforms should no longer be applied.
    effect = Effect("test", lambda _: 0.8).add_steps(
        [duration(0.5, persist_steps=False, steps=[MultiplyValue(0.0)])]
    )
    state = EffectState()

    effect.update(state, make_timer(1.0))  # expire the duration
    value = effect.value(state, 0.0, 1)

    # Multiplier step state cleared: shape value passes through unmodified.
    assert value == pytest.approx(0.8)


# ---------------------------------------------------------------------------
# persist_steps=True — child state survives the reset
# ---------------------------------------------------------------------------


def test_duration_step_preserves_child_transforms_across_cycles_when_persist_is_true() -> None:
    # Child step stores data on the state; with persist_steps=True it should
    # survive the timer reset and keep modifying the output.
    child = MultiplyValue(0.5)
    effect = Effect("test", lambda _: 0.8).add_steps(
        [duration(0.5, persist_steps=True, steps=[child])]
    )
    state = EffectState()

    effect.update(state, make_timer(1.0))  # expire and reset
    value = effect.value(state, 0.0, 1)

    # Child step still applies its transform (0.8 × 0.5 = 0.4).
    assert value == pytest.approx(0.4)


# ---------------------------------------------------------------------------
# Child step sequencing within DurationStep
# ---------------------------------------------------------------------------


def test_duration_step_drives_child_step_updates_each_frame() -> None:
    child = CountUpdates()
    effect = Effect("test").add_steps([duration(1.0, steps=[child])])
    state = EffectState()

    effect.update(state, make_timer(0.1))
    effect.update(state, make_timer(0.1))
    effect.update(state, make_timer(0.1))

    assert child.count == 3
