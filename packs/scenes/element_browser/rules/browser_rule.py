"""Element browser scene — cycles element pages and effect levels."""

from __future__ import annotations

try:
    from typing import Final
except ImportError:
    pass  # typing not available on all embedded runtimes

from engine.engine import GameRule
from engine.input import InputEvents
from engine.state import GameState, Scope

_ELEMENT_PAGES: Final = (
    (
        (Scope.Global.BUFF, "elements.air"),
        (Scope.Global.DEBUFF, "elements.dark"),
        (Scope.Global.MAIN, "elements.earth"),
        (Scope.DIRECTIONAL, "elements.fire"),
        (Scope.PERSONAL, "elements.gravity"),
    ),
    (
        (Scope.Global.BUFF, "elements.ice"),
        (Scope.Global.DEBUFF, "elements.light"),
        (Scope.Global.MAIN, "elements.lightning"),
        (Scope.DIRECTIONAL, "elements.time"),
        (Scope.PERSONAL, "elements.water"),
    ),
)

_PAGE_COUNT: Final = len(_ELEMENT_PAGES)
_MAX_LEVEL: Final = 10


def _apply_page(page: int, level: int, state: GameState) -> None:
    for scope, name in _ELEMENT_PAGES[page]:
        state.effect_controls.set_effect(scope, name, {"level": level})


class ElementBrowserRule(GameRule):
    def __init__(self) -> None:
        self.on(InputEvents.Sensors, self._handle)

    def _handle(self, event: InputEvents.Sensors, state: GameState) -> None:
        if not state.get("shown", False):
            state.set("shown", True)
            _apply_page(state.get("page", 0), state.get("level", 1), state)
            return

        if event.buttons.is_pressed("A"):
            page = (state.get("page", 0) + 1) % _PAGE_COUNT
            state.set("page", page)
            _apply_page(page, state.get("level", 1), state)

        elif event.buttons.is_pressed("B"):
            level = state.get("level", 1) + 1
            if level > _MAX_LEVEL:
                level = 1
            state.set("level", level)
            _apply_page(state.get("page", 0), level, state)


RULE = ElementBrowserRule()
