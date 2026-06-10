"""Hardware verification demo — hardware_test scene on RP2040 PropMaker + IS31FL3741.

Loads the ``hardware_test`` scene via ``SceneManager`` so every hardware subsystem
(LEDs, buttons, accelerometer, IR transceiver, radio, audio, haptics) can be
exercised through the same scene logic used in production.  Each per-mode rule
prints a concise action log to the serial console, giving a text trace
alongside the visual output:

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
- Two buttons (pull-up) on BUTTON_A_PIN / BUTTON_B_PIN (default: D9 / D10)
- LIS3DH I2C accelerometer on default SDA/SCL (shared bus with IS31FL3741)
- IR receiver on IR_RX_PIN; IR LINE emitter on IR_LINE_PIN
- Radio module wired to HardwareNetworkControls
- DRV2605L haptic motor driver on default SDA/SCL (optional — demo runs without it)

Installation
------------
1. Install CircuitPython on your board:
   https://learn.adafruit.com/welcome-to-circuitpython/installing-circuitpython

2. Copy required libraries to CIRCUITPY/lib/:
     adafruit_is31fl3741/
     adafruit_lis3dh.mpy
     adafruit_drv2605.mpy  (optional — required only when a DRV2605L is wired up)

3. Run the deploy script to copy all source files and set code.py:
     python scripts/deploy.py examples/hardware/hw_test_demo.py
   The board reboots and starts running automatically.

Modes (press Button B to cycle)
--------------------------------
Mode 0 — RGB idle
    Five element effects (water, fire, lightning, earth, ice) fill each scope.
    Press A to step the brightness level from 1 → 10 → 1; the console logs
    ``rgb level -> N``.

Mode 1 — Accelerometer
    Accelerometer axes map to scopes: X → PERSONAL (red/cyan),
    Y → DIRECTIONAL (green/magenta), Z → Global.ALL (blue/yellow).
    Tilt the device to change colours and intensity.  The console logs
    ``accel (x, y, z)`` at most ~twice per second.  Button A is a no-op here.

Mode 2 — IR receive
    Press A to transmit a real IR packet via the LINE emitter (blip + haptic
    fire); the console logs ``sending IR packet``.  On a real receive from
    another device, DIRECTIONAL flashes white for 0.5 s, then returns to idle
    solid white, and the console logs
    ``ir received <payload> strength=<s> margin=<m>``.  Note: self-reception on
    a single board is unreliable due to IR LED ↔ receiver AGC bleed — a second
    device or reflective surface is needed for end-to-end verification.

Mode 3 — Radio receive
    Press A to simulate sending a radio packet (queues RadioReceived
    internally); the console logs ``sending radio packet``.  On a receive,
    Global.ALL flashes white for 0.5 s, then returns to the idle solid white,
    and the console logs ``radio received <payload> from <sender>``.

Mode 4 — SFX
    Press A to fire the ``scene.sfx_test`` effect (console logs ``playing
    sfx``), which plays the clip
    ``sounds/sfx_test.wav`` via the I2S amp and triggers a STRONG_CLICK haptic
    pattern on the DRV2605L (if present).  If the WAV file is absent from the
    device filesystem, ``AudioEffectOutput`` silently no-ops; if the DRV2605L is
    not wired, the haptic output is simply absent from the ``EffectManager``.
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
# IR_RX_PIN receives IR pulses from the VS1838 (or equivalent) receiver.
# IR_LINE_PIN drives the LINE emitter LED (38 kHz modulated via PulseOut).
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
_ir_transmitters, _ir_receiver = propmaker.setup_ir(IR_RX_PIN, IR_LINE_PIN)

# ---------------------------------------------------------------------------
# Effect system
# ---------------------------------------------------------------------------

_effect_registry = PackRegistry(item_attr="BUILD")
_effect_registry.scan_dir("packs/effects", "packs.effects")

_rule_registry = PackRegistry(item_attr="RULE")
_rule_registry.scan_dir("packs/rules", "packs.rules")

_audio_registry = AudioRegistry()
_audio_registry.register("sfx_test_start", "sounds/blip.wav")

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
