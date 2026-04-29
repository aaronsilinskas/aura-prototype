from engine.events import Event, EventGroup

try:
    from typing import Final
except ImportError:
    pass


class ButtonData:
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


class MovementData:
    __slots__ = ("x_accel", "y_accel", "z_accel")

    def __init__(self, x_accel: float = 0.0, y_accel: float = 0.0, z_accel: float = 0.0) -> None:
        self.x_accel = x_accel
        self.y_accel = y_accel
        self.z_accel = z_accel

    def __str__(self) -> str:
        return f"MovementData(x={self.x_accel}, y={self.y_accel}, z={self.z_accel})"


NO_MOVEMENT: "Final" = MovementData()


class InputEvents:
    GROUP: "Final" = EventGroup("in")

    class ButtonAndMovement(Event):
        __slots__ = ("buttons", "movement")

        def __init__(self, buttons: ButtonData, movement: MovementData = NO_MOVEMENT) -> None:
            super().__init__(InputEvents.GROUP, "button_and_movement")
            self.buttons = buttons
            self.movement = movement
