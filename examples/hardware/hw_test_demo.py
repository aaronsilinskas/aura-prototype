"""Hardware verification demo — hw_test scene on RP2040 PropMaker + IS31FL3741.

Loads the ``hw_test`` scene via ``SceneManager`` so every hardware subsystem
(LEDs, buttons, accelerometer, IR transceiver, radio) can be exercised through
the same scene logic used in production.  The ``debug`` rules pack logs every
dispatched event to the serial console, giving a text trace alongside the visual
output.

Hardware
--------
- Adafruit RP2040 PropMaker Feather
- Adafruit IS31FL3741 13×9 RGB LED Matrix Breakout (I2C on default SDA/SCL)
- Two buttons (pull-up) on BUTTON_A_PIN / BUTTON_B_PIN (default: D9 / D10)
- LIS3DH I2C accelerometer on default SDA/SCL (shared bus with IS31FL3741)
- IR transceiver wired to HardwareNetworkControls
- Radio module wired to HardwareNetworkControls

Installation
------------
1. Install CircuitPython on your board:
   https://learn.adafruit.com/welcome-to-circuitpython/installing-circuitpython

2. Copy required libraries to CIRCUITPY/lib/:
     adafruit_is31fl3741/
     adafruit_lis3dh.mpy

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
"""

import board

import hardware.circuitpython.propmaker as propmaker
from engine.effects.manager import EffectManager
from engine.engine import GameEngine
from engine.input import AccelerationData, ButtonData, InputEvents
from engine.network import HardwareNetworkControls
from engine.packs import PackRegistry
from engine.scene import SceneManager
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

_i2c = propmaker.setup_i2c()
_matrix = propmaker.setup_matrix_is31fl3741(_i2c)
_button_a, _button_b = propmaker.setup_buttons(BUTTON_A_PIN, BUTTON_B_PIN)
_accelerometer = propmaker.setup_accelerometer(_i2c)

# ---------------------------------------------------------------------------
# Effect system
# ---------------------------------------------------------------------------

_effect_registry = PackRegistry(item_attr="BUILD")
_effect_registry.scan_dir("packs/effects", "packs.effects")

_rule_registry = PackRegistry(item_attr="RULE")
_rule_registry.scan_dir("packs/rules", "packs.rules")

_effect_manager = EffectManager(
    registry=_effect_registry,
    outputs=[IS31FL3741EffectOutput(_matrix)],
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
# Button state tracking
# ---------------------------------------------------------------------------

_button_prev_a = True
_button_prev_b = True

# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

while True:
    # --- Read button state (edge detection: falling edge = PRESSED) ---
    _cur_a = _button_a.value
    _cur_b = _button_b.value

    _btn_states = {}
    if not _cur_a and _button_prev_a:
        _btn_states["A"] = ButtonData.PRESSED
    elif _cur_a and not _button_prev_a:
        _btn_states["A"] = ButtonData.RELEASED
    elif not _cur_a:
        _btn_states["A"] = ButtonData.DOWN
    else:
        _btn_states["A"] = ButtonData.UP

    if not _cur_b and _button_prev_b:
        _btn_states["B"] = ButtonData.PRESSED
    elif _cur_b and not _button_prev_b:
        _btn_states["B"] = ButtonData.RELEASED
    elif not _cur_b:
        _btn_states["B"] = ButtonData.DOWN
    else:
        _btn_states["B"] = ButtonData.UP

    _button_prev_a = _cur_a
    _button_prev_b = _cur_b

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
    if _manager._stack:
        _active_state = _manager._stack[-1][1]
        _active_state.queue_event(
            InputEvents.ButtonAndAcceleration(
                ButtonData(_btn_states),
                _acceleration,
            )
        )

    # --- Advance game rules ---
    _manager.update()

    # --- Advance effect rendering ---
    _effect_manager.update(_engine._timer)
