"""CircuitPython hardware demo — RP2040 PropMaker + IS31FL3741 13×9 LED matrix.

Two element pages cycle across all five scopes on the LED matrix.
- Button A: advance to the next element page
- Button B: increase effect level (1–10, wraps to 1)
FPS is printed to serial each second.

Hardware
--------
- Adafruit RP2040 PropMaker Feather
- Adafruit IS31FL3741 13×9 RGB LED Matrix Breakout (I2C on default SDA/SCL)
- Button A on GP9 (pull-up) — page forward
- Button B on GP10 (pull-up) — level up

Installation
------------
1. Install CircuitPython on your PropMaker board:
   https://learn.adafruit.com/adafruit-feather-rp2040-prop-maker

2. Copy the following libraries to CIRCUITPY/lib/:
     adafruit_is31fl3741/

3. Copy the effects/ and engine/ directories to the CIRCUITPY drive root so
   they live at /CIRCUITPY/effects/ and /CIRCUITPY/engine/.

4. Copy this file to /CIRCUITPY/code.py.
   The board reboots and starts running automatically.
"""

import time

import board

import hardware.circuitpython.propmaker as propmaker
from engine.effects.manager import EffectManager
from engine.engine import GameEngine, GameRule, Version
from engine.input import ButtonData, InputEvents
from engine.packs import PackRegistry
from engine.state import SceneControls, Scope
from engine.timer import Timer
from hardware.circuitpython.is31fl3741_output import IS31FL3741EffectOutput

try:
    from typing import Final
except ImportError:
    pass

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

BUTTON_A_PIN: "Final" = board.D9
BUTTON_B_PIN: "Final" = board.D10

# ---------------------------------------------------------------------------
# Hardware setup
# ---------------------------------------------------------------------------

_i2c = propmaker.setup_i2c()
_matrix = propmaker.setup_matrix_is31fl3741(_i2c)
_buttons = propmaker.setup_buttons(BUTTON_A_PIN, BUTTON_B_PIN)

# ---------------------------------------------------------------------------
# Element pages
# ---------------------------------------------------------------------------

# Two pages, each mapping five scopes to element names in order:
# BUFF, DEBUFF, MAIN, DIRECTIONAL, PERSONAL
_ELEMENT_PAGES = (
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

# ---------------------------------------------------------------------------
# Effect system
# ---------------------------------------------------------------------------

_registry = PackRegistry(item_attr="BUILD")
_registry.scan_dir("packs/effects", "packs.effects")


class ButtonEffectRule(GameRule):
    def __init__(self):
        super().__init__("button_effects", Version(1, 0))
        self.on(InputEvents.ButtonAndAcceleration, self._on_buttons)

    def _on_buttons(self, event, state):
        button_data = event.buttons
        if button_data.states["A"] == ButtonData.PRESSED:
            page = (state.get("demo_page", 0) + 1) % 2
            level = state.get("demo_level", 1)
            state.set("demo_page", page)
            for scope, name in _ELEMENT_PAGES[page]:
                state.effect_controls.set_effect(scope, name, level, {})
        elif button_data.states["B"] == ButtonData.PRESSED:
            page = state.get("demo_page", 0)
            level = state.get("demo_level", 1) + 1
            if level > 10:
                level = 1
            state.set("demo_level", level)
            for scope, name in _ELEMENT_PAGES[page]:
                state.effect_controls.set_effect(scope, name, level, {})


effect_output = IS31FL3741EffectOutput(_matrix)
effect_manager = EffectManager(
    registry=_registry,
    outputs=[effect_output],
)

game_engine = GameEngine(effect_controls=effect_manager)
game_engine.add_rules(ButtonEffectRule())
game_state = game_engine.create_state(SceneControls())

# Display page 0 at level 1 before entering the main loop
for _scope, _name in _ELEMENT_PAGES[0]:
    effect_manager.set_effect(_scope, _name, 1, {})

# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

timer = Timer()
_fps_frame_count = 0
_fps_window_start = time.monotonic()
while True:
    timer.update()
    effect_manager.update(timer)

    _button_data = _buttons.update(timer.elapsed)
    game_state.queue_event(InputEvents.ButtonAndAcceleration(_button_data))

    game_engine.update(game_state)

    _fps_frame_count += 1
    _fps_now = time.monotonic()
    if _fps_now - _fps_window_start >= 1.0:
        print("FPS:", _fps_frame_count)
        _fps_frame_count = 0
        _fps_window_start = _fps_now
