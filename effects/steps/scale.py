from effects.effect import EffectState, EffectStep, EffectTimer
from effects.value import DynamicValue, Range, ValueGenerator


class MultiplierStep(EffectStep):
    """Scales the output value from a start to an end multiplier over the step's timer duration.

    Useful for fading an effect in or out, or modulating intensity over time.
    """

    def __init__(self, start: DynamicValue, end: DynamicValue):
        self.start = start
        self.end = end

    class _Data:
        __slots__ = ("multiplier", "range")

        def __init__(self, start: float, end: float):
            self.range: Range = Range(start, end)
            self.multiplier: float = start

    def update(self, state: EffectState, timer: EffectTimer) -> bool:
        data = state.get_step_data(self, MultiplierStep._Data)
        if data is None:
            data = self._Data(
                ValueGenerator.resolve(self.start),
                ValueGenerator.resolve(self.end),
            )
            state.set_step_data(self, data)
        data.multiplier = data.range.lerp(timer.progress)

        if timer.progress >= 1.0:
            state.remove_step_data(self)

        return True

    def adjust_value(self, state: EffectState, position: float, value: float) -> float:
        data = state.get_step_data(self, MultiplierStep._Data)
        if data is not None:
            return value * data.multiplier

        return value


def multiplier(start: DynamicValue, end: DynamicValue) -> EffectStep:
    """Return a step that scales output value from ``start`` to ``end`` over the timer duration."""
    return MultiplierStep(start, end)
