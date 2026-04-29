try:
    from collections.abc import Callable
except ImportError:
    pass  # No typing support on CircuitPython yet

from effects.effect import EffectState, EffectStep, EffectTimer
from effects.value import DynamicValue, ValueGenerator


class HideStep(EffectStep):
    """Suppresses all output for a fixed duration, then advances to the next step.

    While active, ``adjust_value`` returns ``0.0`` regardless of the effect shape.
    """

    def __init__(self, duration: DynamicValue):
        self.duration = duration

    def update(self, state: EffectState, timer: EffectTimer) -> bool:
        duration_timer = state.get_step_data(self, EffectTimer)
        if duration_timer is None:
            duration_timer = EffectTimer(duration=ValueGenerator.resolve(self.duration))
            state.set_step_data(self, duration_timer)

        if duration_timer.update(timer.elapsed):
            state.remove_step_data(self)
            return True

        return False

    def adjust_value(self, state: EffectState, position: float, value: float) -> float:
        if state.get_step_data(self, EffectTimer) is not None:
            return 0.0

        return value


def hide(duration: DynamicValue) -> EffectStep:
    """Return a step that holds output at ``0.0`` for ``duration`` seconds, then advances."""
    return HideStep(duration)


class CallStep(EffectStep):
    """Invokes a callback once when activated, then immediately advances to the next step.

    Useful for triggering side effects (e.g. notifying listeners like a sound effects player)
    at a specific point in a step sequence without pausing the effect.
    """

    def __init__(self, callback: Callable[[EffectState, EffectTimer], None]):
        self.callback = callback

    def update(self, state: EffectState, timer: EffectTimer) -> bool:
        self.callback(state, timer)
        return True


def call(callback: Callable[[EffectState, EffectTimer], None]) -> EffectStep:
    """Return a step that invokes ``callback`` once when activated, then advances."""
    return CallStep(callback)
