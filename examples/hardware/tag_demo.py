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
          "game_over_sting_start": "sounds/game_over.wav",
          "fire_shot_start": "sounds/blip.wav",
          "scene.hit_start": "sounds/blip.wav",
          "reload": "sounds/blip.wav",
          "reload_complete": "sounds/blip.wav"
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

from engine.effects.manager import EffectManager
from engine.engine import GameEngine
from engine.input import AccelerationData, InputEvents
from engine.network import NetworkEvents
from engine.packs import PackRegistry
from engine.scene import SceneManager, SceneRegistry
from engine.timer import Timer
from hardware.circuitpython.device_builder import build_hardware, load_device_config
from hardware.shared.tag_protocol import TagInfraredDecoder, TagInfraredEncoder

# ---------------------------------------------------------------------------
# Hardware setup (config-driven; tag scene uses Tag IR codec)
# ---------------------------------------------------------------------------

_config = load_device_config()
_hw = build_hardware(
    _config,
    ir_encoder=TagInfraredEncoder(),
    ir_decoder=TagInfraredDecoder(),
)

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
_manager.load("tag")
_manager.update()  # applies the load transition; tag scene is now active

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

    # --- Poll IR receiver and queue any received packets ---
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

    # --- Queue combined input event ---
    if _manager.active_state is not None:
        _manager.active_state.queue_event(
            InputEvents.ButtonAndAcceleration(
                _button_data,
                _acceleration,
            )
        )

    # --- Advance game rules ---
    _manager.update()

    # --- Advance effect rendering ---
    _effect_manager.update(_timer)
