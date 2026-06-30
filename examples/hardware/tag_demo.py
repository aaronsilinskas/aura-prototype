"""Infrared Tag mini-game demo — RP2040 PropMaker Feather + IS31FL3741.

Runs the ``tag`` scene: boots to Ready, starts on a button press, runs a
five-pulse warning countdown, then drops into Playing with a 10-hitpoint
progress bar. Button A in Playing fires a tag shot via the LINE IR emitter
using the infrared tag protocol (``hardware.shared.tag_protocol``).

Hardware
--------
- Adafruit RP2040 PropMaker Feather
- Adafruit IS31FL3741 13x9 RGB LED Matrix Breakout (I2C on default SDA/SCL)
- Two buttons (pull-up) — default: D9 / D10 (set via aura-device.json)
- IR receiver and LINE IR emitter (set via aura-device.json)
- DRV2605L haptic motor driver on default SDA/SCL (optional - demo runs without it)

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
      "ir": {"rx": "D11", "line": "D12"},
      "audio": {
        "voices": 4,
        "max_volume": 0.1,
        "clips": {
          "warning_pulse_peak": "sounds/blip.wav",
          "go_start": "sounds/blip.wav",
          "game_over_sting_start": "sounds/game_over.wav",
          "fire_shot_start": "sounds/blip.wav",
          "scene.hit_start": "sounds/blip.wav",
          "reload": "sounds/blip.wav",
          "reload_complete": "sounds/blip.wav",
          "dry_fire_start": "sounds/blip.wav",
          "ready_shots_start": "sounds/blip.wav"
        }
      }
    }

Installation
------------
1. Install CircuitPython on your board:
   https://learn.adafruit.com/welcome-to-circuitpython/installing-circuitpython

2. Copy required libraries to CIRCUITPY/lib/:
     adafruit_is31fl3741/
     adafruit_drv2605.mpy  (optional - required only when a DRV2605L is wired up)

3. Run the deploy script to copy all source files and set code.py:
     python scripts/deploy.py examples/hardware/tag_demo.py
   The board reboots and starts running automatically.

How to play
-----------
- Press A or B in Ready to start the countdown.
- After the warning pulses finish, Playing begins with 10 hitpoints.
- Press A in Playing to fire a tag shot via the LINE IR emitter.
"""

from hardware.shared.scene_runtime import run_scene
from hardware.shared.tag_protocol import TagInfraredDecoder, TagInfraredEncoder

run_scene("tag", ir_encoder=TagInfraredEncoder(), ir_decoder=TagInfraredDecoder())
