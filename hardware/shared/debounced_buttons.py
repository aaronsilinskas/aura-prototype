try:
    from collections.abc import Callable
except ImportError:
    pass

from engine.input import ButtonData


class _ButtonState:
    """Per-button debounce state.

    ``candidate_time`` accumulates how long ``candidate`` has held stable.
    """

    __slots__ = ("candidate", "candidate_time", "settled")

    def __init__(self, initial: bool) -> None:
        self.settled = initial
        self.candidate = initial
        self.candidate_time = 0.0


class DebouncedButtons:
    """Time-based button debouncer using pull-up semantics.

    Accepts a list of (label, predicate) pairs where each predicate returns the
    raw pin value: ``True`` = HIGH (button not pressed), ``False`` = LOW (button
    pressed).

    Falling edge (HIGH → LOW) commits as ``PRESSED``; rising edge (LOW → HIGH)
    commits as ``RELEASED``.  A candidate must remain stable for ``interval``
    seconds before being committed so that transient noise is ignored.

    Each predicate is sampled once at construction to seed the settled state,
    preventing spurious ``PRESSED`` events for buttons already held at boot.
    """

    __slots__ = ("_interval", "_predicates", "_states")

    def __init__(
        self,
        buttons: "list[tuple[str, Callable[[], bool]]]",
        interval: float = 0.05,
    ) -> None:
        self._interval = interval
        self._predicates = buttons
        self._states = [_ButtonState(pred()) for _, pred in buttons]

    def update(self, elapsed: float, out: ButtonData) -> None:
        """Advance debounce state by ``elapsed`` seconds and write results into *out*.

        The caller pre-creates *out* before the loop and passes the same instance every frame.
        """
        for i, (label, pred) in enumerate(self._predicates):
            state = self._states[i]
            current = pred()
            if current != state.candidate:
                state.candidate = current
                state.candidate_time = 0.0
            state.candidate_time += elapsed
            if state.candidate != state.settled and state.candidate_time >= self._interval:
                state.settled = state.candidate
                out.set(label, ButtonData.PRESSED if not state.settled else ButtonData.RELEASED)
            else:
                out.set(label, ButtonData.DOWN if not state.settled else ButtonData.UP)
