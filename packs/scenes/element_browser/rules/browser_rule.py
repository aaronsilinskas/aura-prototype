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


def _warm_all_pages(state: GameState) -> None:
    """Pre-import every page's effect modules while the boot heap is still fresh.

    On CircuitPython the first import of an element module invokes the compiler,
    which needs a large contiguous heap block.  Doing it lazily on the first
    switch to a later page crashes with ``MemoryError`` once the current page's
    live effects have fragmented the heap.  Warming every module up front at
    scene setup moves that one-time compile spike off the page-switch path.
    """
    for page in _ELEMENT_PAGES:
        for _scope, name in page:
            state.effect_controls.warm_effect(name)


class ElementBrowserRule(GameRule):
    def __init__(self) -> None:
        self.on(InputEvents.ButtonAndAcceleration, self._handle)

    def _handle(self, event: InputEvents.ButtonAndAcceleration, state: GameState) -> None:
        if not state.get("shown", False):
            state.set("shown", True)
            _warm_all_pages(state)
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
