"""Red Light Green Light mini-game — RP2040 PropMaker Feather + IS31FL3741.

Runs the Red Light, Green Light mini-game scene on a PropMaker Feather with an IS31FL3741 LED
matrix.  The accelerometer detects player motion so the game can catch cheaters
moving on a red light.

Hardware
--------
- Adafruit RP2040 PropMaker Feather
- Adafruit IS31FL3741 13×9 RGB LED Matrix Breakout (I2C on default SDA/SCL)
- Two buttons (pull-up) — default: D9 / D10 (set via aura-device.json)
- LIS3DH I2C accelerometer on default SDA/SCL (shared bus with IS31FL3741)
- DRV2605L haptic motor driver on default SDA/SCL (optional — game runs without it)

Configuration
-------------
Deploy an ``aura-device.json`` to the CIRCUITPY drive root.  Example::

    {
      "pixels": {
        "type": "matrix",
        "cols": 13,
        "scope_rows": {
          "global.buff": [0, 1], "global.debuff": [1, 2],
          "global.main": [2, 5], "personal": [5, 7],
          "directional": [7, 8], "ambient": [8, 9]
        }
      },
      "buttons": ["D9", "D10"],
      "audio": {
        "voices": 2,
        "max_volume": 0.1,
        "clips": {
          "ready_start": "sounds/red_light_green_light.wav",
          "warning_sting_peak": "sounds/blip.wav",
          "red_light_music_start": "sounds/rlgl_stop_music.wav",
          "green_light_music_start": "sounds/rlgl_go_music.wav",
          "game_over_sting_start": "sounds/game_over.wav",
          "win_sting_start": "sounds/game_won.wav",
          "level_up_start": "sounds/level_up.wav"
        }
      }
    }

Installation
------------
1. Install CircuitPython on your board:
   https://learn.adafruit.com/welcome-to-circuitpython/installing-circuitpython

2. Copy required libraries to CIRCUITPY/lib/:
     adafruit_is31fl3741/
     adafruit_lis3dh.mpy
     adafruit_drv2605.mpy  (optional — required only when a DRV2605L is wired up)

3. Run the deploy script to copy all source files and set code.py:
     python scripts/deploy.py examples/hardware/red_light_green_light_demo.py
   The board reboots and starts running automatically.

How to play
-----------
- Press A or B to start the game.
- Green light: keep moving — detected via accelerometer.
- Red light: freeze completely — any detected motion is penalised.
- The LED matrix shows the current game state (green / red / result).
"""

from engine.effects.manager import EffectManager
from engine.engine import GameEngine
from engine.input import AccelerationData, InputEvents
from engine.packs import PackRegistry
from engine.scene import SceneManager, SceneRegistry
from engine.timer import Timer
from hardware.circuitpython.device_builder import build_hardware, load_device_config

# ---------------------------------------------------------------------------
# Hardware setup (config-driven)
# ---------------------------------------------------------------------------

_config = load_device_config()
_hw = build_hardware(_config)

# ---------------------------------------------------------------------------
# Effect system
# ---------------------------------------------------------------------------

_effect_registry = PackRegistry(item_attr="BUILD")
_effect_registry.scan_dir("packs/effects", "packs.effects")

_rule_registry = PackRegistry(item_attr="RULE")
_rule_registry.scan_dir("packs/rules", "packs.rules")

_effect_manager = EffectManager(
    registry=_effect_registry,
    outputs=_hw.outputs,
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

_timer = Timer()

while True:
    _timer.update()

    # --- Read button state ---
    _button_data = _hw.buttons.update(_timer.elapsed)

    # --- Read accelerometer ---
    _acceleration = None
    if _hw.accelerometer is not None:
        try:
            _ax, _ay, _az = _hw.accelerometer.acceleration
            _acceleration = AccelerationData(_ax, _ay, _az)
        except Exception:
            pass

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
    _effect_manager.update(_timer)
