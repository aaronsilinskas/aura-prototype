import pytest
from effects.tests.helpers import make_timer

from effects.effect import Effect, EffectState
from effects.steps.position import VelocitySharedData, face_forward


def test_face_forward_leaves_position_unchanged_when_moving_forward() -> None:
    state = EffectState()
    vel = VelocitySharedData.get(state)
    vel.rotations_per_second = 1.0

    effect = Effect("test", lambda pos: pos).add_steps([face_forward()])

    effect.update(state, make_timer(0.1))
    value = effect.value(state, 0.3)

    assert value == pytest.approx(0.3)


def test_face_forward_mirrors_position_when_moving_in_reverse() -> None:
    state = EffectState()
    vel = VelocitySharedData.get(state)
    vel.rotations_per_second = -1.0

    effect = Effect("test", lambda pos: pos).add_steps([face_forward()])

    effect.update(state, make_timer(0.1))
    value = effect.value(state, 0.3)

    # reversed: 1.0 - 0.3 = 0.7
    assert value == pytest.approx(0.7)
