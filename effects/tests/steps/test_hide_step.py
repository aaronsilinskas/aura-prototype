import pytest

from effects.effect import Effect, EffectState
from effects.steps.control import hide
from effects.tests.helpers import RecordAndHold, make_timer


def test_hide_suppresses_output_while_duration_is_active() -> None:
    effect = Effect("test", lambda _: 1.0).add_steps([hide(1.0)])
    state = EffectState()

    effect.update(state, make_timer(0.1))
    value = effect.value(state, 0.0, 1)

    assert value == pytest.approx(0.0)


def test_hide_restores_output_after_duration_expires() -> None:
    effect = Effect("test", lambda _: 0.8).add_steps([hide(0.5)])
    state = EffectState()

    effect.update(state, make_timer(1.0))  # far exceeds duration
    value = effect.value(state, 0.0, 1)

    assert value == pytest.approx(0.8)


def test_hide_advances_to_next_step_after_duration_expires() -> None:
    log: list = []
    effect = Effect("test").add_steps([hide(0.5), RecordAndHold("next", log)])
    state = EffectState()

    effect.update(state, make_timer(1.0))

    assert log == ["next"]


def test_hide_does_not_advance_before_duration_expires() -> None:
    log: list = []
    effect = Effect("test").add_steps([hide(1.0), RecordAndHold("next", log)])
    state = EffectState()

    effect.update(state, make_timer(0.4))

    assert log == []


def test_hide_accumulates_elapsed_time_across_frames() -> None:
    log: list = []
    effect = Effect("test").add_steps([hide(0.5), RecordAndHold("next", log)])
    state = EffectState()

    effect.update(state, make_timer(0.3))
    effect.update(state, make_timer(0.3))  # total 0.6s > 0.5s duration

    assert log == ["next"]
