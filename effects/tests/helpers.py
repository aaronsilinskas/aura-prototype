from effects.effect import EffectState, EffectStep, EffectTimer


class AlwaysAdvance(EffectStep):
    """Step that immediately yields control to the next step every frame."""

    def update(self, state: EffectState, timer: EffectTimer) -> bool:
        return True


class NeverAdvance(EffectStep):
    """Step that stays active indefinitely."""

    def update(self, state: EffectState, timer: EffectTimer) -> bool:
        return False


class OffsetPosition(EffectStep):
    """Shifts the sampling position by a fixed amount while active."""

    def __init__(self, offset: float):
        self._offset = offset

    def update(self, state: EffectState, timer: EffectTimer) -> bool:
        # Returns True so the effect immediately advances past this step each
        # frame.  The transform still applies because Effect.value() calls
        # adjust_position on ALL steps regardless of which step is active.
        return True

    def adjust_position(self, state: EffectState, position: float) -> float:
        return position + self._offset


class MultiplyValue(EffectStep):
    """Scales the output value by a fixed factor while active."""

    def __init__(self, factor: float):
        self._factor = factor

    def update(self, state: EffectState, timer: EffectTimer) -> bool:
        # Returns True so the effect immediately advances past this step each
        # frame.  The transform still applies because Effect.value() calls
        # adjust_value on ALL steps regardless of which step is active.
        return True

    def adjust_value(self, state: EffectState, position: float, value: float) -> float:
        return value * self._factor


class RecordAndHold(EffectStep):
    """Records a label to a shared log each time it is updated, then holds."""

    def __init__(self, label: str, log: list):
        self._label = label
        self._log = log

    def update(self, state: EffectState, timer: EffectTimer) -> bool:
        self._log.append(self._label)
        return False


class CountUpdates(EffectStep):
    """Counts how many times update is called on it."""

    def __init__(self):
        self.count = 0

    def update(self, state: EffectState, timer: EffectTimer) -> bool:
        self.count += 1
        return False


def make_timer(elapsed: float) -> EffectTimer:
    """Return an EffectTimer that has already been advanced by ``elapsed`` seconds."""
    t = EffectTimer()
    t.update(elapsed)
    return t
