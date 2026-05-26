"""CircuitPython hardware demo — RP2040 PropMaker + IS31FL3741 13×9 LED matrix.

A fire effect is hardcoded at startup and rendered across the LED matrix.
Subsequent issues add button input (#34), audio output (#35), and FPS
reporting (#36).

Hardware
--------
- Adafruit RP2040 PropMaker Feather
- Adafruit IS31FL3741 13×9 RGB LED Matrix Breakout (I2C on default SDA/SCL)

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

Configuration
-------------
- Buttons A–D on GP9–GP12 (pull-up) layer effects or clear all.
"""

import time

import board

import hardware.circuitpython.propmaker as propmaker
from engine.effects.manager import EffectManager
from engine.engine import GameEngine, GameRule, Version
from engine.input import ButtonData, InputEvents, MovementData
from engine.packs import PackRegistry
from engine.state import SceneControls, Scope
from engine.timer import Timer
from hardware.circuitpython.audio_output import AudioEffectOutput
from hardware.circuitpython.is31fl3741_output import IS31FL3741EffectOutput

try:
    from typing import Final
except ImportError:
    pass

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_BUTTON_NAMES = ("A", "B", "C", "D")

BUTTON_A_PIN: "Final" = board.D9
BUTTON_B_PIN: "Final" = board.D10
BUTTON_C_PIN: "Final" = board.D11
BUTTON_D_PIN: "Final" = board.D12

# ---------------------------------------------------------------------------
# Hardware setup
# ---------------------------------------------------------------------------

_i2c = propmaker.setup_i2c()
_matrix = propmaker.setup_matrix_is31fl3741(_i2c)
_button_a, _button_b, _button_c, _button_d = propmaker.setup_buttons(
    BUTTON_A_PIN, BUTTON_B_PIN, BUTTON_C_PIN, BUTTON_D_PIN
)
propmaker.setup_external_power()

# ---------------------------------------------------------------------------
# Effect system
# ---------------------------------------------------------------------------

_registry = PackRegistry(item_attr="BUILD")
_registry.scan_dir("packs/effects", "packs.effects")


class ButtonEffectRule(GameRule):
    def __init__(self):
        super().__init__("button_effects", Version(1, 0))

    def handle_event(self, event, state):
        if isinstance(event, InputEvents.ButtonAndMovement):
            button_data = event.buttons
            if button_data.states["A"] == ButtonData.PRESSED:
                state.effect_controls.add_effect(Scope.PERSONAL, "elements.fire", 5, {})
            elif button_data.states["B"] == ButtonData.PRESSED:
                state.effect_controls.add_effect(Scope.PERSONAL, "elements.water", 5, {})
            elif button_data.states["C"] == ButtonData.PRESSED:
                state.effect_controls.add_effect(Scope.PERSONAL, "elements.lightning", 2, {})
            elif button_data.states["D"] == ButtonData.PRESSED:
                state.effect_controls.stop_effect(Scope.ALL)


effect_output = IS31FL3741EffectOutput(_matrix)
audio_output = AudioEffectOutput()
effect_manager = EffectManager(
    registry=_registry,
    outputs=[effect_output, audio_output],
)

game_engine = GameEngine(effect_controls=effect_manager)
game_engine.add_rules(ButtonEffectRule())
game_state = game_engine.create_state(SceneControls())

# Button state tracking for edge detection (pull-up: True = not pressed)
_buttons = [_button_a, _button_b, _button_c, _button_d]
_button_prev = [True, True, True, True]

# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

timer = Timer()
_fps_frame_count = 0
_fps_window_start = time.monotonic()
while True:
    timer.update()
    effect_manager.update(timer)

    for _i, _btn in enumerate(_buttons):
        _current = _btn.value
        if not _current and _button_prev[_i]:  # falling edge: just pressed
            _states = dict.fromkeys(_BUTTON_NAMES, ButtonData.UP)
            _states[_BUTTON_NAMES[_i]] = ButtonData.PRESSED
            game_state.queue_event(
                InputEvents.ButtonAndMovement(ButtonData(_states), MovementData())
            )
        _button_prev[_i] = _current

    game_engine.update(game_state)

    _fps_frame_count += 1
    _fps_now = time.monotonic()
    if _fps_now - _fps_window_start >= 1.0:
        print("FPS:", _fps_frame_count)
        _fps_frame_count = 0
        _fps_window_start = _fps_now
