import select
import sys
import termios
import time
import tty

from effects.elements.registry import build_element_renderer
from effects.manager.manager import EffectBuilder, EffectManager, EffectOutput
from effects.manager.scope import Scope
from effects.render import EffectRenderer, PixelBuffer, RendererConfig
from engine.engine import GameEngine, GameRule, GameState
from engine.events import Event
from engine.input import ButtonData, InputEvents, MovementData
from engine.timer import Timer


class ElementEffectBuilder(EffectBuilder):
    def __call__(self, name: str, config: RendererConfig) -> EffectRenderer:
        return build_element_renderer(name, config)


class AnsiEffectOutput(EffectOutput):
    PIXEL_COUNT = 36

    def __init__(self, scopes: list) -> None:
        self.min_resolution = self.PIXEL_COUNT
        self.scopes = scopes

    def create_buffer(self) -> PixelBuffer:
        return PixelBuffer(self.PIXEL_COUNT)

    def update_pixels(self, frames: list) -> None:
        if not frames:
            print("\r" + "  " * self.PIXEL_COUNT, end="", flush=True)
            return
        buf = frames[0]
        parts = []
        for color in buf:
            r = (color >> 16) & 0xFF
            g = (color >> 8) & 0xFF
            b = color & 0xFF
            parts.append(f"\033[48;2;{r};{g};{b}m  \033[0m")
        print("\r" + "".join(parts), end="", flush=True)


personal_output = AnsiEffectOutput(scopes=[Scope.PERSONAL])
effect_manager = EffectManager(builder=ElementEffectBuilder(), outputs=[personal_output])

game_engine = GameEngine()


class MakeEffectRule(GameRule):
    def __init__(self, manager: EffectManager) -> None:
        self._manager = manager

    def handle_event(self, event: Event, state: GameState) -> None:
        if isinstance(event, InputEvents.ButtonAndMovement):
            button_data = event.buttons
            if button_data.states["A"] == ButtonData.PRESSED:
                self._manager.set_effect(Scope.PERSONAL, "fire", 5, {})
            elif button_data.states["B"] == ButtonData.PRESSED:
                self._manager.set_effect(Scope.PERSONAL, "water", 5, {})


game_engine.add_rules(MakeEffectRule(effect_manager))

# - TODO: Single container object to pass all params to rules (engine, state, effect manager, etc)
# - TODO: New standardized effect event name design for sound/vibration triggers

_default_movement = MovementData(x_accel=0.0, y_accel=9.8, z_accel=0.0)


def _make_event(key: str | None) -> InputEvents.ButtonAndMovement:
    if key in ("a", "A"):
        states = {"A": ButtonData.PRESSED, "B": ButtonData.UP}
    elif key in ("b", "B"):
        states = {"A": ButtonData.UP, "B": ButtonData.PRESSED}
    else:
        states = {"A": ButtonData.UP, "B": ButtonData.UP}
    return InputEvents.ButtonAndMovement(ButtonData(states=states), _default_movement)


def main() -> None:
    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        print("Press 'a' (fire), 'b' (water), 'q' to quit.\r")
        timer = Timer()
        while True:
            timer.update()
            key = None
            if select.select([sys.stdin], [], [], 0)[0]:
                key = sys.stdin.read(1)
                if key == "q":
                    break
            game_engine.queue_event(_make_event(key))
            game_engine.update(timer)
            effect_manager.update(timer)
            time.sleep(0.033)  # ~30 fps
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
        print()


main()


