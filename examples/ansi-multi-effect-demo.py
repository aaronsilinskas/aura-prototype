import os
import select
import sys
import termios
import time
import tty

from effects.effect import Effect, PixelBuffer
from engine.effects.manager import EffectManager
from engine.effects.output import EffectOutput
from engine.engine import GameEngine, GameRule
from engine.events import EffectEvent, Event
from engine.input import AccelerationData, ButtonData, InputEvents
from engine.packs import PackRegistry
from engine.state import EffectReceipt, GameState, SceneControls, Scope, ScopeValue
from engine.timer import Timer

_packs_dir = os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "packs", "effects")
)
_registry = PackRegistry(item_attr="BUILD")
_registry.scan_dir(_packs_dir, "packs.effects")


BLOCK_HEIGHT = 2  # 1 pixel line (layered effects already split/merged into it) + 1 event line


class AnsiEffectOutput(EffectOutput):
    PIXEL_COUNT = 36

    def __init__(self, scopes: list[ScopeValue]) -> None:
        super().__init__()
        self.min_resolution = self.PIXEL_COUNT
        self.scopes = scopes
        self._initialized = False
        self._last_event: str = ""
        self._event_count: int = 0

    def create_buffer(self, scope_key: str) -> PixelBuffer:
        return PixelBuffer(self.PIXEL_COUNT)

    def handle_event(
        self,
        event: EffectEvent,
        scope_keys: frozenset[str],
        effect: Effect,
        receipt: EffectReceipt,
    ) -> None:
        self._last_event = str(event)
        self._event_count += 1

    def update_pixels(self, scope_key: str, buffer: PixelBuffer) -> None:
        parts = []
        for color in buffer:
            r = (color >> 16) & 0xFF
            g = (color >> 8) & 0xFF
            b = color & 0xFF
            parts.append(f"\033[48;2;{r};{g};{b}m  \033[0m")
        pixel_line = "\r" + "".join(parts)
        event_line = (
            f"\r[audio #{self._event_count}] {self._last_event}\033[K"
            if self._last_event
            else "\r\033[K"
        )
        lines = [pixel_line, event_line]
        if self._initialized:
            print(f"\033[{BLOCK_HEIGHT}A", end="")
        else:
            self._initialized = True
        print("\r\n".join(lines), end="")

    def flush(self) -> None:
        sys.stdout.flush()


personal_output = AnsiEffectOutput(scopes=[Scope.PERSONAL])
effect_manager = EffectManager(registry=_registry, outputs=[personal_output])
# Standalone demo, no SceneManager -- declare every scanned pack allowed so
# pack.effect names below resolve (see issue #814: EffectAdmin.set_allowed_packs).
effect_manager.set_allowed_packs(frozenset(_registry.names()))

game_engine = GameEngine(effect_controls=effect_manager)
game_state = game_engine.create_state(SceneControls())


class MakeEffectRule(GameRule):
    def handle_event(self, event: Event, state: GameState) -> None:
        if isinstance(event, InputEvents.ButtonAndAcceleration):
            button_data = event.buttons
            if button_data.is_pressed("A"):
                state.effect_controls.add_effect(Scope.PERSONAL, "elements.fire", {"level": 5})
            elif button_data.is_pressed("B"):
                state.effect_controls.add_effect(Scope.PERSONAL, "elements.water", {"level": 5})
            elif button_data.is_pressed("C"):
                state.effect_controls.add_effect(Scope.PERSONAL, "elements.lightning", {"level": 5})
            elif button_data.is_pressed("D"):
                state.effect_controls.stop_effect(Scope.ALL)


game_engine.add_rules(MakeEffectRule())

_default_acceleration = AccelerationData(x=0.0, y=9.8, z=0.0)


def _make_event(key: str | None) -> InputEvents.ButtonAndAcceleration:
    pressed = key.upper() if key else None
    states = {
        button: ButtonData.PRESSED if button == pressed else ButtonData.UP
        for button in ("A", "B", "C", "D")
    }
    return InputEvents.ButtonAndAcceleration(ButtonData(states=states), _default_acceleration)


def main() -> None:
    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        print("Press 'a' (fire), 'b' (water), 'c' (lightning), 'd' (stop all), 'q' to quit.\r")
        timer = Timer()
        while True:
            timer.update()
            key = None
            if select.select([sys.stdin], [], [], 0)[0]:
                key = sys.stdin.read(1)
                if key == "q":
                    break
            game_state.queue_event(_make_event(key))
            game_engine.update(game_state)
            effect_manager.update(timer)
            time.sleep(0.033)  # ~30 fps
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
        print()


main()
