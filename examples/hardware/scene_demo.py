"""Config-selected scene loader — RP2040 PropMaker Feather + IS31FL3741.

Loads whichever scene ``aura-device.json`` names and runs it with the default
(Aura) IR wire-frame.  This is a thin entry point: it resolves the scene name
from config and hands off to ``app.scene_runtime.run_scene``, which owns
hardware bring-up and the main loop.

Scene selection
---------------
Add an optional top-level ``"scene"`` string to ``aura-device.json``::

    {
      "scene": "red_light_green_light",
      "pixels": [ ... ],
      "buttons": ["D9", "D10"]
    }

A missing, empty, or non-string ``"scene"`` value falls back to the
``hardware_test`` scene.  An unknown name (not in the scene registry) logs the
known scenes to the console and also falls back to ``hardware_test`` rather than
crashing.  ``DeviceConfig`` carries no ``scene`` field — the key is read from the
raw mapping here and ignored by ``parse_device_config``.

Hardware
--------
- Adafruit RP2040 PropMaker Feather
- Adafruit IS31FL3741 13×9 RGB LED Matrix Breakout (I2C on default SDA/SCL)
- Buttons, LIS3DH accelerometer, IR transceiver, DRV2605L haptics — all wired
  per ``aura-device.json`` (required; the device has no built-in default)

Installation
------------
1. Install CircuitPython on your board:
   https://learn.adafruit.com/welcome-to-circuitpython/installing-circuitpython

2. Copy required libraries to CIRCUITPY/lib/:
     adafruit_is31fl3741/
     adafruit_lis3dh.mpy
     adafruit_drv2605.mpy  (optional)

3. Place ``aura-device.json`` in CIRCUITPY/ to declare pin/geometry and select
   a scene via the ``"scene"`` key. It is required — the device has no built-in
   default. Copy ``examples/aura-device.sample.json`` as a starting point.

4. Run the deploy script to copy all source files and set code.py:
     python scripts/deploy.py examples/hardware/scene_demo.py
   The board reboots and starts running automatically.
"""

from app.scene_runtime import run_scene
from hardware.shared.device_config import read_device_config_mapping
from hardware.shared.scene_selection import resolve_scene_name

run_scene(resolve_scene_name(read_device_config_mapping()))
