"""Config-selected scene loader — RP2040 PropMaker Feather + IS31FL3741.

Loads whichever scene is resolved at boot and runs it with the default (Aura)
IR wire-frame.  This is a thin entry point: it hands straight off to
``app.scene_runtime.run_scene``, which owns hardware bring-up, boot-scene
resolution, and the main loop.

Scene selection
---------------
Add a ``"default_scene"`` string to ``aura-settings.json``, kept alongside
``aura-device.json`` on CIRCUITPY::

    {
      "default_scene": "red_light_green_light"
    }

``run_scene`` resolves the boot scene only after hardware is brought up (so
the SD card, if any, is mounted): a ``scene`` value persisted to the SD
card's ``aura-state.json`` overrides this flash ``default_scene``; a
card-less device, or one with nothing persisted, boots the flash default
unaffected.  There is no code-level default scene: when neither a persisted
selection nor a flash default is set, boot raises and stops.  An unknown
name (not in the scene registry) also raises, naming the known scenes,
rather than silently running a fallback scene.  ``DeviceConfig`` carries no
``scene`` field — the hardware config (``aura-device.json``) has nothing to
do with scene selection.

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

3. Place ``aura-device.json`` in CIRCUITPY/ to declare pin/geometry, and
   ``aura-settings.json`` to select a scene via the ``"default_scene"`` key.
   Both are required — the device has no built-in default for either. Copy
   ``examples/aura-device.rasppi-pico-2.json`` and ``examples/aura-settings.json``
   as starting points.

4. Run the deploy script to copy all source files and set code.py:
     python scripts/deploy.py examples/hardware/scene_demo.py
   The board reboots and starts running automatically.
"""

from app.scene_runtime import run_scene

run_scene()
