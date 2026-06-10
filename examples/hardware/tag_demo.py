"""Infrared Tag mini-game demo — RP2040 PropMaker Feather + IS31FL3741.

Runs the ``tag`` scene: boots to Ready, starts on a button press, runs a
five-pulse warning countdown, then drops into Playing with a 10-hitpoint
progress bar. Button A in Playing fires a tag shot via the LINE IR emitter
using the infrared tag protocol (``hardware.shared.tag_protocol``).

Hardware
--------
- Adafruit RP2040 PropMaker Feather
- Adafruit IS31FL3741 13x9 RGB LED Matrix Breakout (I2C on default SDA/SCL)
- Two buttons (pull-up) on BUTTON_A_PIN / BUTTON_B_PIN (default: D9 / D10)
- IR receiver on IR_RX_PIN; IR LINE emitter on IR_LINE_PIN
- DRV2605L haptic motor driver on default SDA/SCL (optional - demo runs without it)

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

import time as _time

import board

import hardware.circuitpython.propmaker as propmaker
from engine.audio import AudioRegistry
from engine.effects.manager import EffectManager
from engine.engine import GameEngine
from engine.input import AccelerationData, InputEvents
from engine.network import HardwareNetworkControls, NetworkEvents
from engine.packs import PackRegistry
from engine.scene import SceneManager, SceneRegistry
from hardware.circuitpython.audio_output import AudioEffectOutput
from hardware.circuitpython.drv2605_output import Drv2605EffectOutput
from hardware.circuitpython.is31fl3741_output import IS31FL3741EffectOutput
from hardware.shared.tag_protocol import TagInfraredDecoder, TagInfraredEncoder

try:
    from typing import Final
except ImportError:
    pass

# ---------------------------------------------------------------------------
# Configuration — adjust to match your wiring
# ---------------------------------------------------------------------------

BUTTON_A_PIN: "Final" = board.D9
BUTTON_B_PIN: "Final" = board.D10

# IR transceiver pins — update these to match your board layout.
IR_RX_PIN: "Final" = board.D11
IR_LINE_PIN: "Final" = board.D12

# ---------------------------------------------------------------------------
# Hardware setup
# ---------------------------------------------------------------------------

propmaker.setup_external_power()
_i2c = propmaker.setup_i2c()
_matrix = propmaker.setup_matrix_is31fl3741(_i2c)
_buttons = propmaker.setup_buttons(BUTTON_A_PIN, BUTTON_B_PIN)
_accelerometer = propmaker.setup_accelerometer(_i2c)
_motor = propmaker.setup_drv2605(_i2c)
_ir_transmitters, _ir_receiver = propmaker.setup_ir(
    IR_RX_PIN,
    IR_LINE_PIN,
    encoder=TagInfraredEncoder(),
    decoder=TagInfraredDecoder(),
)

# ---------------------------------------------------------------------------
# Effect system
# ---------------------------------------------------------------------------

_effect_registry = PackRegistry(item_attr="BUILD")
_effect_registry.scan_dir("packs/effects", "packs.effects")

_rule_registry = PackRegistry(item_attr="RULE")
_rule_registry.scan_dir("packs/rules", "packs.rules")

_audio_registry = AudioRegistry()
_audio_registry.register("warning_pulse_peak", "sounds/blip.wav")
_audio_registry.register("game_over_sting_start", "sounds/game_over.wav")

_audio_output = AudioEffectOutput(_audio_registry, max_volume=0.1, num_voices=1)
_outputs = [IS31FL3741EffectOutput(_matrix), _audio_output]
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
    network_controls=HardwareNetworkControls(_ir_transmitters),
)

_scene_registry = SceneRegistry()
_scene_registry.scan_dir("packs/scenes", "packs.scenes")

_manager = SceneManager(_engine, _effect_registry, _rule_registry, _scene_registry)
_manager.load("tag")
_manager.update()  # applies the load transition; tag scene is now active

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

    # --- Poll IR receiver and queue any received packets ---
    if _manager.active_state is not None:
        _ir_data = _ir_receiver.receive()
        if _ir_data is not None:
            _manager.active_state.queue_event(
                NetworkEvents.IRReceived(
                    _ir_data,
                    _ir_receiver.last_signal_strength,
                    _ir_receiver.last_error_margin,
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
    _effect_manager.update(_engine._timer)
