"""Red Light Green Light mini-game — RP2040 PropMaker Feather + IS31FL3741.

Runs the Red Light, Green Light mini-game scene on a PropMaker Feather with an IS31FL3741 LED
matrix.  The accelerometer detects player motion so the game can catch cheaters
moving on a red light.

Hardware
--------
- Adafruit RP2040 PropMaker Feather
- Adafruit IS31FL3741 13×9 RGB LED Matrix Breakout (I2C on default SDA/SCL)
- Two buttons (pull-up) on BUTTON_A_PIN / BUTTON_B_PIN (default: D9 / D10)
- LIS3DH I2C accelerometer on default SDA/SCL (shared bus with IS31FL3741)
- DRV2605L haptic motor driver on default SDA/SCL (optional — game runs without it)

Installation
------------
1. Install CircuitPython on your board:
   https://learn.adafruit.com/welcome-to-circuitpython/installing-circuitpython

2. Copy required libraries to CIRCUITPY/lib/:
     adafruit_is31fl3741/
     adafruit_lis3dh.mpy
     adafruit_drv2605.mpy  (optional — required only when a DRV2605L is wired up)

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

import time as _time

import board

import hardware.circuitpython.propmaker as propmaker
from engine.audio import AudioRegistry
from engine.effects.manager import EffectManager
from engine.engine import GameEngine
from engine.input import AccelerationData, InputEvents
from engine.packs import PackRegistry
from engine.scene import SceneManager, SceneRegistry
from hardware.circuitpython.audio_output import AudioEffectOutput
from hardware.circuitpython.drv2605_output import Drv2605EffectOutput
from hardware.circuitpython.is31fl3741_output import (
    IS31FL3741_COLS,
    IS31FL3741_SCOPE_ROWS,
    IS31FL3741EffectOutput,
)

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

propmaker.setup_external_power()
_i2c = propmaker.setup_i2c()
_matrix = propmaker.setup_matrix_is31fl3741(_i2c)
_buttons = propmaker.setup_buttons(BUTTON_A_PIN, BUTTON_B_PIN)
_accelerometer = propmaker.setup_accelerometer(_i2c)
_motor = propmaker.setup_drv2605(_i2c)

# ---------------------------------------------------------------------------
# Effect system
# ---------------------------------------------------------------------------

_effect_registry = PackRegistry(item_attr="BUILD")
_effect_registry.scan_dir("packs/effects", "packs.effects")

_rule_registry = PackRegistry(item_attr="RULE")
_rule_registry.scan_dir("packs/rules", "packs.rules")

_audio_registry = AudioRegistry()
_audio_registry.register("ready_start", "sounds/red_light_green_light.wav")
_audio_registry.register("warning_sting_peak", "sounds/blip.wav")
_audio_registry.register("red_light_music_start", "sounds/rlgl_stop_music.wav")
_audio_registry.register("green_light_music_start", "sounds/rlgl_go_music.wav")
_audio_registry.register("game_over_sting_start", "sounds/game_over.wav")
_audio_registry.register("win_sting_start", "sounds/game_won.wav")
_audio_registry.register("level_up_start", "sounds/level_up.wav")

_audio_output = AudioEffectOutput(
    _audio_registry,
    max_volume=0.1,
    num_voices=2,
    i2s_bit_clock=board.I2S_BIT_CLOCK,
    i2s_word_select=board.I2S_WORD_SELECT,
    i2s_data=board.I2S_DATA,
)
_outputs = [
    IS31FL3741EffectOutput(_matrix, cols=IS31FL3741_COLS, scope_rows=IS31FL3741_SCOPE_ROWS),
    _audio_output,
]
if _motor is not None:
    _outputs.append(Drv2605EffectOutput(_motor))

_effect_manager = EffectManager(
    registry=_effect_registry,
    outputs=_outputs,
)

# ---------------------------------------------------------------------------
# Game engine and scene manager
# ---------------------------------------------------------------------------

_engine = GameEngine(
    effect_controls=_effect_manager,
)

_scene_registry = SceneRegistry()
_scene_registry.scan_dir("packs/scenes", "packs.scenes")

_scene_manager = SceneManager(_engine, _effect_registry, _rule_registry, _scene_registry)
_scene_manager.load("red_light_green_light")
_scene_manager.update()  # applies the load transition; red_light_green_light scene is now active

# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

_last_tick = _time.monotonic()

while True:
    _now = _time.monotonic()
    elapsed = _now - _last_tick
    _last_tick = _now

    # --- Read button state ---
    _button_data = _buttons.update(elapsed)

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
                _button_data,
                _acceleration,
            )
        )

    # --- Advance game rules ---
    _scene_manager.update()

    # --- Advance effect rendering ---
    _effect_manager.update(_engine._timer)
