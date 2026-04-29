import pytest
from effects.tests.helpers import make_timer

from effects.effect import Effect, EffectState
from effects.steps.position import set_position


def test_set_position_shifts_sampling_position_by_fixed_amount() -> None:
    # Shape returns position as value so we can observe the sampled position directly.
    effect = Effect("test", lambda pos: pos % 1.0).add_steps([set_position(0.2)])
    state = EffectState()

    effect.update(state, make_timer(0.1))
    value = effect.value(state, 0.5)

    assert value == pytest.approx(0.7)


def test_set_position_wraps_position_when_offset_exceeds_one() -> None:
    effect = Effect("test", lambda pos: pos % 1.0).add_steps([set_position(0.3)])
    state = EffectState()

    effect.update(state, make_timer(0.1))
    value = effect.value(state, 0.8)

    assert value == pytest.approx(0.1)
