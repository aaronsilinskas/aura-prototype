"""Hardware verification demo — hw_test scene on RP2040 PropMaker + IS31FL3741.

Loads the ``hw_test`` scene via ``SceneManager`` so every hardware subsystem
(LEDs, buttons, accelerometer, IR transceiver, radio, audio, haptics) can be
exercised through the same scene logic used in production.  The ``debug`` rules
pack logs every dispatched event to the serial console, giving a text trace
alongside the visual output.

Hardware
--------
- Adafruit RP2040 PropMaker Feather
- Adafruit IS31FL3741 13×9 RGB LED Matrix Breakout (I2C on default SDA/SCL)
- Two buttons (pull-up) on BUTTON_A_PIN / BUTTON_B_PIN (default: D9 / D10)
- LIS3DH I2C accelerometer on default SDA/SCL (shared bus with IS31FL3741)
- IR transceiver wired to HardwareNetworkControls
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
    Press A to step the brightness level from 1 → 10 → 1.

Mode 1 — Accelerometer
    Accelerometer axes map to scopes: X → PERSONAL (red/cyan),
    Y → DIRECTIONAL (green/magenta), Z → Global.ALL (blue/yellow).
    Tilt the device to change colours and intensity.

Mode 2 — IR receive
    Press A to simulate sending an IR packet (queues IRReceived internally).
    On a real receive, DIRECTIONAL flashes white at level 9 for 0.5 s, then
    returns to the idle solid white.  Console shows ``net.ir_received``.

Mode 3 — Radio receive
    Press A to simulate sending a radio packet (queues RadioReceived internally).
    On a real receive, Global.ALL flashes white at level 9 for 0.5 s, then
    returns to the idle solid white.  Console shows ``net.radio_received``.

Mode 4 — SFX
    Press A to fire the ``hw_test.sfx_test`` effect, which plays the clip
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
from engine.network import HardwareNetworkControls
from engine.packs import PackRegistry
from engine.scene import SceneManager
from hardware.circuitpython.audio_output import AudioEffectOutput
from hardware.circuitpython.drv2605_output import Drv2605EffectOutput
from hardware.circuitpython.is31fl3741_output import IS31FL3741EffectOutput
from scenes.hw_test.scene import factory as hw_test_factory

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
_audio_registry.register("sfx_test_start", "sounds/sfx_test.wav")

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
    network_controls=HardwareNetworkControls(),
)

_manager = SceneManager(_engine, _effect_registry, _rule_registry)
_manager.register("hw_test", hw_test_factory)
_manager.load("hw_test")
_manager.update()  # applies the load transition; hw_test scene is now active

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
