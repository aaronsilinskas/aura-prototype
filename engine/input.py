from engine.events import Event, EventGroup

try:
    from typing import Final
except ImportError:
    pass


class ButtonData:
    """Reusable buffer of button states, overwritten in place each poll.

    ``_states`` maps button name to one of the class constants:
    ``UP``, ``DOWN``, ``PRESSED`` (transitioned down this frame), or
    ``RELEASED`` (transitioned up this frame).

    This buffer is mutated each frame via ``set`` — it is not a cross-frame
    snapshot.  Callers that need to retain values across frames must copy.

    Use the query methods (``is_pressed``, ``is_released``, ``is_down``,
    ``is_up``) instead of accessing ``_states`` directly.  ``get`` and
    ``items`` are provided for callers that need the raw constant or need to
    iterate over all buttons.
    """

    __slots__ = ("_states",)

    UP: "Final" = 0
    DOWN: "Final" = 1
    PRESSED: "Final" = 2
    RELEASED: "Final" = 3

    def __init__(self, states: dict[str, int]) -> None:
        self._states = states

    # ------------------------------------------------------------------
    # Mutation
    # ------------------------------------------------------------------

    def set(self, name: str, state: int) -> None:
        self._states[name] = state

    # ------------------------------------------------------------------
    # Query helpers
    # ------------------------------------------------------------------

    def is_pressed(self, name: str) -> bool:
        """Return ``True`` if *name* transitioned to pressed this frame."""
        return self._states.get(name) == self.PRESSED

    def is_released(self, name: str) -> bool:
        """Return ``True`` if *name* transitioned to released this frame."""
        return self._states.get(name) == self.RELEASED

    def is_down(self, name: str) -> bool:
        """Return ``True`` if *name* is physically held (``DOWN`` or ``PRESSED``)."""
        state = self._states.get(name)
        return state == self.DOWN or state == self.PRESSED

    def is_up(self, name: str) -> bool:
        """Return ``True`` if *name* is not held (``UP`` or ``RELEASED``)."""
        state = self._states.get(name)
        return state == self.UP or state == self.RELEASED

    def get(self, name: str) -> int | None:
        """Return the raw state constant for *name*, or ``None`` if unknown."""
        return self._states.get(name)

    def items(self):  # type: ignore[return]  # ItemsView not available on CircuitPython/MicroPython
        """Iterate over ``(button_name, state)`` pairs for all buttons."""
        return self._states.items()

    def __str__(self) -> str:
        state_names = {
            self.UP: "UP",
            self.DOWN: "DOWN",
            self.PRESSED: "PRESSED",
            self.RELEASED: "RELEASED",
        }
        parts = ", ".join(f"{k}={state_names.get(v, v)}" for k, v in self._states.items())
        return f"ButtonData({parts})"


class AccelerationData:
    """Reusable buffer of accelerometer readings, overwritten in place each poll.

    Unit of measure is meters per second squared (m/s²). Axes follow the
    device's local coordinate system. ``None`` in place of an instance signals
    that no accelerometer hardware is present — transient read failures retain
    the last good reading rather than replacing the buffer with ``None``.
    """

    __slots__ = ("x", "y", "z")

    GRAVITY: "Final" = 9.81  # m/s²

    def __init__(self, x: float = 0.0, y: float = 0.0, z: float = 0.0) -> None:
        self.x = x
        self.y = y
        self.z = z

    def __str__(self) -> str:
        return f"AccelerationData(x={self.x}, y={self.y}, z={self.z})"


class InputEvents:
    """Namespace for input-layer event types."""

    GROUP: "Final" = EventGroup("in")

    class ButtonAndAcceleration(Event):
        """Event carrying button state and optional acceleration data.

        Fired each input poll cycle. The same instance is reused every frame;
        ``buttons`` and ``acceleration`` are mutated in place before each
        dispatch. ``acceleration`` is ``None`` only when the device has no
        accelerometer hardware — transient read failures retain the last good
        reading rather than setting ``None``.
        """

        __slots__ = ("acceleration", "buttons")

        def __init__(
            self, buttons: ButtonData, acceleration: "AccelerationData | None" = None
        ) -> None:
            super().__init__(InputEvents.GROUP, "button_and_acceleration")
            self.buttons = buttons
            self.acceleration = acceleration
