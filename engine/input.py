from engine.events import Event, EventGroup

try:
    from typing import Final
except ImportError:
    pass


class ButtonData:
    """Snapshot of button states at a point in time.

    ``states`` maps button name to one of the class constants:
    ``UP``, ``DOWN``, ``PRESSED`` (transitioned down this frame), or
    ``RELEASED`` (transitioned up this frame).
    """

    __slots__ = ("states",)

    UP: "Final" = 0
    DOWN: "Final" = 1
    PRESSED: "Final" = 2
    RELEASED: "Final" = 3

    def __init__(self, states: dict[str, int]) -> None:
        self.states = states

    def __str__(self) -> str:
        state_names = {
            self.UP: "UP",
            self.DOWN: "DOWN",
            self.PRESSED: "PRESSED",
            self.RELEASED: "RELEASED",
        }
        parts = ", ".join(f"{k}={state_names.get(v, v)}" for k, v in self.states.items())
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
