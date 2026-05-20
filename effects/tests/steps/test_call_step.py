from effects.effect import Effect, EffectState, EffectTimer
from effects.steps.control import call
from effects.tests.helpers import RecordAndHold, make_timer


def test_call_invokes_callback_when_step_is_activated() -> None:
    calls: list = []
    effect = Effect("test").add_steps([call(lambda s, t: calls.append(1))])
    state = EffectState()

    effect.update(state, make_timer(0.016))

    assert len(calls) == 1


def test_call_advances_immediately_without_delaying_the_frame() -> None:
    log: list = []
    effect = Effect("test").add_steps(
        [
            call(lambda s, t: None),
            RecordAndHold("next", log),
        ]
    )
    state = EffectState()

    effect.update(state, make_timer(0.016))

    assert log == ["next"]


def test_call_passes_state_and_timer_to_callback() -> None:
    received: list = []
    effect = Effect("test").add_steps([call(lambda s, t: received.extend([s, t]))])
    state = EffectState()
    timer = make_timer(0.016)

    effect.update(state, timer)

    assert received[0] is state
    assert isinstance(received[1], EffectTimer)
