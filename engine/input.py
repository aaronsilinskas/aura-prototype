from engine.events import Event, EventGroup

try:
    from typing import Final
except ImportError:
    pass


class ButtonData:
    """Snapshot of button states at a point in time.

    ``_states`` maps button name to one of the class constants:
    ``UP``, ``DOWN``, ``PRESSED`` (transitioned down this frame), or
    ``RELEASED`` (transitioned up this frame).

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
    """Snapshot of accelerometer readings at a point in time. Unit of measure is meters per second
    squared (m/s^2).

    Axes follow the device's local coordinate system. When no accelerometer is
    present or a read fails, use ``None`` rather than an ``AccelerationData``
    instance — ``None`` signals "no sensor data", not "device at rest".
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
        """Event carrying a button state snapshot and optional acceleration data.

        Fired each input poll cycle. ``acceleration`` is ``None`` when the
        device has no accelerometer or when a transient read failure occurs.
        """

        __slots__ = ("acceleration", "buttons")

        def __init__(
            self, buttons: ButtonData, acceleration: "AccelerationData | None" = None
        ) -> None:
            super().__init__(InputEvents.GROUP, "button_and_acceleration")
            self.buttons = buttons
            self.acceleration = acceleration
