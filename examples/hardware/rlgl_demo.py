"""Red Light Green Light mini-game — RP2040 PropMaker Feather + IS31FL3741.

Runs the RLGL mini-game scene on a PropMaker Feather with an IS31FL3741 LED
matrix.  The accelerometer detects player motion so the game can catch cheaters
moving on a red light.

Hardware
--------
- Adafruit RP2040 PropMaker Feather
- Adafruit IS31FL3741 13×9 RGB LED Matrix Breakout (I2C on default SDA/SCL)
- Two buttons (pull-up) on BUTTON_A_PIN / BUTTON_B_PIN (default: D9 / D10)
- LIS3DH I2C accelerometer on default SDA/SCL (shared bus with IS31FL3741)

Installation
------------
1. Install CircuitPython on your board:
   https://learn.adafruit.com/welcome-to-circuitpython/installing-circuitpython

2. Copy required libraries to CIRCUITPY/lib/:
     adafruit_is31fl3741/
     adafruit_lis3dh.mpy

3. Run the deploy script to copy all source files and set code.py:
     python scripts/deploy.py examples/hardware/rlgl_demo.py
   The board reboots and starts running automatically.

How to play
-----------
- Press A or B to start the game.
- Green light: keep moving — detected via accelerometer.
- Red light: freeze completely — any detected motion is penalised.
- The LED matrix shows the current game state (green / red / result).
"""

import board

import hardware.circuitpython.propmaker as propmaker
from engine.effects.manager import EffectManager
from engine.engine import GameEngine
from engine.input import AccelerationData, ButtonData, InputEvents
from engine.packs import PackRegistry
from engine.scene import SceneManager
from hardware.circuitpython.is31fl3741_output import IS31FL3741EffectOutput
from scenes.rlgl.scene import factory as rlgl_factory

try:
    from typing import Final
except ImportError:
    pass

# ---------------------------------------------------------------------------
# Configuration — adjust to match your wiring
# ---------------------------------------------------------------------------

BUTTON_A_PIN: "Final" = board.D9
BUTTON_B_PIN: "Final" = board.D10

# ---------------------------------------------------------------------------
# Hardware setup
# ---------------------------------------------------------------------------

_i2c = propmaker.setup_i2c()
_matrix = propmaker.setup_matrix_is31fl3741(_i2c)
_button_a, _button_b = propmaker.setup_buttons(BUTTON_A_PIN, BUTTON_B_PIN)
_accelerometer = propmaker.setup_accelerometer(_i2c)

# ---------------------------------------------------------------------------
# Effect system
# ---------------------------------------------------------------------------

_effect_registry = PackRegistry(item_attr="BUILD")
_effect_registry.scan_dir("packs/effects", "packs.effects")

_rule_registry = PackRegistry(item_attr="RULE")
_rule_registry.scan_dir("packs/rules", "packs.rules")

_effect_manager = EffectManager(
    registry=_effect_registry,
    outputs=[IS31FL3741EffectOutput(_matrix)],
)

# ---------------------------------------------------------------------------
# Game engine and scene manager
# ---------------------------------------------------------------------------

_engine = GameEngine(
    effect_controls=_effect_manager,
)

_scene_manager = SceneManager(_engine, _effect_registry, _rule_registry)
_scene_manager.register("rlgl", rlgl_factory)
_scene_manager.load("rlgl")
_scene_manager.update()  # applies the load transition; rlgl scene is now active

# ---------------------------------------------------------------------------
# Button state tracking
# ---------------------------------------------------------------------------

_button_prev_a = True
_button_prev_b = True

# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

while True:
    # --- Read button state (edge detection: falling edge = PRESSED) ---
    _cur_a = _button_a.value
    _cur_b = _button_b.value

    _btn_states = {}
    if not _cur_a and _button_prev_a:
        _btn_states["A"] = ButtonData.PRESSED
    elif _cur_a and not _button_prev_a:
        _btn_states["A"] = ButtonData.RELEASED
    elif not _cur_a:
        _btn_states["A"] = ButtonData.DOWN
    else:
        _btn_states["A"] = ButtonData.UP

    if not _cur_b and _button_prev_b:
        _btn_states["B"] = ButtonData.PRESSED
    elif _cur_b and not _button_prev_b:
        _btn_states["B"] = ButtonData.RELEASED
    elif not _cur_b:
        _btn_states["B"] = ButtonData.DOWN
    else:
        _btn_states["B"] = ButtonData.UP

    _button_prev_a = _cur_a
    _button_prev_b = _cur_b

    # --- Read accelerometer ---
    if _accelerometer is not None:
        try:
            _ax, _ay, _az = _accelerometer.acceleration
            _acceleration = AccelerationData(_ax, _ay, _az)
        except Exception:
            _acceleration = None
    else:
        _acceleration = None

    # --- Queue combined input event ---
    if _scene_manager.active_state is not None:
        _scene_manager.active_state.queue_event(
            InputEvents.ButtonAndAcceleration(
                ButtonData(_btn_states),
                _acceleration,
            )
        )

    # --- Advance game rules ---
    _scene_manager.update()

    # --- Advance effect rendering ---
    _effect_manager.update(_engine._timer)
