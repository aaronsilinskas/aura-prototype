"""Hardware verification demo — hardware_test scene on RP2040 PropMaker + IS31FL3741.

Boots entirely from ``aura-device.json`` (falls back to the stock PropMaker +
IS31FL3741 defaults when the file is absent).  The ``hardware_test`` scene
exercises every hardware subsystem (LEDs, buttons, accelerometer, IR
transceiver, audio, haptics) and logs progress to the serial console.

- Button B: ``changing to mode N``
- Mode 0 Button A: ``rgb level -> N``
- Mode 1 (each ~0.5 s): ``accel (x, y, z)``
- Mode 2 Button A: ``sending IR packet``; on receive:
  ``ir received <payload> strength=<s> margin=<m>``
- Mode 3 Button A: ``sending radio packet``; on receive:
  ``radio received <payload> from <sender>``
- Mode 4 Button A: ``playing sfx``

Hardware
--------
- Adafruit RP2040 PropMaker Feather
- Adafruit IS31FL3741 13×9 RGB LED Matrix Breakout (I2C on default SDA/SCL)
- Buttons, LIS3DH accelerometer, IR transceiver, DRV2605L haptics — all wired
  per ``aura-device.json`` (or defaults when the file is absent)

Installation
------------
1. Install CircuitPython on your board:
   https://learn.adafruit.com/welcome-to-circuitpython/installing-circuitpython

2. Copy required libraries to CIRCUITPY/lib/:
     adafruit_is31fl3741/
     adafruit_lis3dh.mpy
     adafruit_drv2605.mpy  (optional)

3. Optionally place ``aura-device.json`` in CIRCUITPY/ to override pin/geometry
   defaults.

4. Run the deploy script to copy all source files and set code.py:
     python scripts/deploy.py examples/hardware/hardware_test_demo.py
   The board reboots and starts running automatically.

Modes (press Button B to cycle)
--------------------------------
Mode 0 — RGB idle: five element effects fill each scope; press A to step brightness.
Mode 1 — Accelerometer: tilt maps to scope colours; logged ~twice per second.
Mode 2 — IR receive: press A to transmit; on receive logs signal strength.
Mode 3 — Radio receive: press A to simulate send; on receive logs sender.
Mode 4 — SFX: press A to fire sfx_test effect.
"""

import time as _time

from engine.effects.manager import EffectManager
from engine.engine import GameEngine
from engine.input import AccelerationData, InputEvents
from engine.network import NetworkEvents
from engine.packs import PackRegistry
from engine.scene import SceneManager, SceneRegistry
from hardware.circuitpython.device_builder import build_hardware, load_device_config

# ---------------------------------------------------------------------------
# Config + hardware
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
    network_controls=_hw.network_controls,
)

_scene_registry = SceneRegistry()
_scene_registry.scan_dir("packs/scenes", "packs.scenes")

_manager = SceneManager(_engine, _effect_registry, _rule_registry, _scene_registry)
_manager.load("hardware_test")
_manager.update()  # applies the load transition; hardware_test scene is now active

# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

_last_tick = _time.monotonic()

while True:
    _now = _time.monotonic()
    elapsed = _now - _last_tick
    _last_tick = _now

    _button_data = _hw.buttons.update(elapsed)

    if _hw.accelerometer is not None:
        try:
            _ax, _ay, _az = _hw.accelerometer.acceleration
            _acceleration = AccelerationData(_ax, _ay, _az)
        except Exception:
            _acceleration = None
    else:
        _acceleration = None

    if _manager.active_state is not None and _hw.ir_receiver is not None:
        _ir_data = _hw.ir_receiver.receive()
        if _ir_data is not None:
            _manager.active_state.queue_event(
                NetworkEvents.IRReceived(
                    _ir_data,
                    _hw.ir_receiver.last_signal_strength,
                    _hw.ir_receiver.last_error_margin,
                    best_receiver=None,
                )
            )

    if _manager.active_state is not None:
        _manager.active_state.queue_event(
            InputEvents.ButtonAndAcceleration(
                _button_data,
                _acceleration,
            )
        )

    _manager.update()

    _effect_manager.update(_engine._timer)
