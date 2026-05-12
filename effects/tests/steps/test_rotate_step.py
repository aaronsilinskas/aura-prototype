import pytest

from effects.effect import Effect, EffectState
from effects.steps.position import rotate
from effects.tests.helpers import make_timer


def test_rotate_shifts_position_proportional_to_speed_and_elapsed() -> None:
    # Shape returns position so we can observe how much the offset shifted it.
    effect = Effect("test", lambda pos: pos % 1.0).add_steps([rotate(2.0)])
    state = EffectState()

    effect.update(state, make_timer(0.3))
    value = effect.value(state, 0.0, 1)

    # offset = 2.0 rps * 0.3 s = 0.6
    assert value == pytest.approx(0.6)


def test_rotate_accumulates_offset_across_multiple_frames() -> None:
    effect = Effect("test", lambda pos: pos % 1.0).add_steps([rotate(1.0)])
    state = EffectState()

    effect.update(state, make_timer(0.3))
    effect.update(state, make_timer(0.3))
    value = effect.value(state, 0.0, 1)

    # offset = 0.3 + 0.3 = 0.6
    assert value == pytest.approx(0.6)


def test_rotate_wraps_accumulated_offset_within_unit_range() -> None:
    effect = Effect("test", lambda pos: pos % 1.0).add_steps([rotate(1.0)])
    state = EffectState()

    effect.update(state, make_timer(1.7))
    value = effect.value(state, 0.0, 1)

    # offset = 1.7 % 1.0 = 0.7
    assert value == pytest.approx(0.7)
