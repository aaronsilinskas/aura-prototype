try:
    from collections.abc import Iterable
except ImportError:
    pass  # No typing support on CircuitPython yet

from effects.effect import EffectState, EffectStep, EffectTimer, run_step_updates
from effects.value import DynamicValue, ValueGenerator


class DurationStep(EffectStep):
    """Runs a timed sub-sequence of steps, then advances to the next step.

    Child steps are updated and sampled for the configured duration. When the
    timer expires, the step advances. If ``persist_steps`` is ``True``, child
    step state is preserved across repetitions; otherwise it is cleared.

    This is the primary way to give an effect a finite lifespan or to sequence
    timed phases (e.g. fade-in, hold, fade-out).
    """

    def __init__(
        self,
        duration: DynamicValue,
        persist_steps: bool,
        steps: Iterable[EffectStep],
    ):
        self.duration = duration
        self.persist_steps = persist_steps
        self.steps = list(steps)

    class _Data:
        __slots__ = ("step_index", "timer")

        def __init__(self, duration: float):
            self.timer = EffectTimer(duration=duration)
            self.step_index: int = 0

    def update(self, state: EffectState, timer: EffectTimer) -> bool:
        data = state.get_step_data(self, DurationStep._Data)
        if data is None:
            data = self._Data(ValueGenerator.resolve(self.duration))
            state.set_step_data(self, data)

        # update the timer used by child steps
        data.timer.update(timer.elapsed)

        # run the child steps sequentially and advance the active step as needed
        data.step_index = run_step_updates(
            self.steps, data.step_index, state, data.timer
        )

        if data.timer.progress >= 1.0:
            if self.persist_steps:
                # reset the duration state, but allow child steps transformations to persist
                data = self._Data(ValueGenerator.resolve(self.duration))
                state.set_step_data(self, data)
            else:
                # clear the duration state, which removes child step transformations
                state.remove_step_data(self)
            return True

        return False

    def adjust_position(self, state: EffectState, position: float) -> float:
        data = state.get_step_data(self, DurationStep._Data)
        if data is not None:
            for step in self.steps:
                position = step.adjust_position(state, position)

        return position

    def adjust_value(self, state: EffectState, position: float, value: float) -> float:
        data = state.get_step_data(self, DurationStep._Data)
        if data is not None:
            for step in self.steps:
                value = step.adjust_value(state, position, value)

        return value


def duration(
    duration: DynamicValue,
    persist_steps: bool = False,
    steps: Iterable[EffectStep] = (),
) -> EffectStep:
    """Return a step that runs ``steps`` for ``duration`` seconds then advances."""
    return DurationStep(duration, persist_steps, steps)
