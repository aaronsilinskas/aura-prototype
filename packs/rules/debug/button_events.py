from __future__ import annotations

from engine.engine import GameRule, Version
from engine.events import Event
from engine.input import ButtonData, InputEvents
from engine.state import GameState

_VERSION: Version = Version(1, 0)


class ButtonEventsRule(GameRule):
    """Triggers events based on per-button state combinations."""

    __slots__ = ("_down", "_pressed", "_released", "_up")

    def __init__(
        self,
        button_pressed: dict[str, Event] | None = None,
        button_down: dict[str, Event] | None = None,
        button_up: dict[str, Event] | None = None,
        button_released: dict[str, Event] | None = None,
    ) -> None:
        super().__init__("debug.button_event", _VERSION)
        self._pressed = button_pressed
        self._down = button_down
        self._up = button_up
        self._released = button_released
        self.on(InputEvents.ButtonAndAcceleration, self._handle_button_input)

    def _handle_button_input(
        self, event: InputEvents.ButtonAndAcceleration, state: GameState
    ) -> None:
        for button_name, button_state in event.buttons.states.items():
            if button_state == ButtonData.PRESSED:
                state_map = self._pressed
            elif button_state == ButtonData.DOWN:
                state_map = self._down
            elif button_state == ButtonData.UP:
                state_map = self._up
            elif button_state == ButtonData.RELEASED:
                state_map = self._released
            else:
                state_map = None
            if state_map is not None:
                button_event = state_map.get(button_name)
                if button_event is not None:
                    state.queue_event(button_event)


RULE = ButtonEventsRule()
