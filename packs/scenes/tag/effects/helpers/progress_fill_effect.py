from effects.layers.progress_layer import ProgressLayer
from effects.layers.progress_renderer import ProgressRenderer


class ProgressFillEffect(ProgressRenderer):
    """A progress fill that runs from empty to full over ``duration`` on its own clock.

    Advances with each ``update``, so it need not be re-issued every tick. A
    zero ``duration`` is full on the first ``update``.
    """

    __slots__ = ("_bar", "_duration", "_elapsed")

    def __init__(self, layer: ProgressLayer, color: int, duration: float) -> None:
        super().__init__(layer, color)
        self._bar = layer
        self._duration = duration
        self._elapsed = 0.0

    def update(self, elapsed: float) -> None:
        self._elapsed += elapsed
        duration = self._duration
        if duration <= 0.0:
            progress = 1.0
        else:
            progress = self._elapsed / duration
            if progress > 1.0:
                progress = 1.0
        self._bar.set_progress(progress)
