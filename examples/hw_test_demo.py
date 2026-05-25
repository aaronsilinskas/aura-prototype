"""Hardware verification demo — hw_test scene on RP2040 PropMaker + IS31FL3741.

Loads the ``hw_test`` scene via ``SceneManager`` so every hardware subsystem
(LEDs, buttons, IMU, IR transceiver, radio) can be exercised through the same
scene logic used in production.  The ``debug`` rules pack logs every dispatched
event to the serial console, giving a text trace alongside the visual output.

Hardware
--------
- Adafruit RP2040 PropMaker Feather
- Adafruit IS31FL3741 13×9 RGB LED Matrix Breakout (I2C on default SDA/SCL)
- Two buttons (pull-up) on BUTTON_A_PIN / BUTTON_B_PIN (default: D9 / D10)
- LIS3DH or compatible I2C accelerometer on default SDA/SCL
- IR transceiver wired to HardwareNetworkControls
- Radio module wired to HardwareNetworkControls

Installation
------------
1. Install CircuitPython on your board:
   https://learn.adafruit.com/welcome-to-circuitpython/installing-circuitpython

2. Copy required libraries to CIRCUITPY/lib/:
     adafruit_is31fl3741/
     adafruit_lis3dh.mpy   (or substitute your IMU library)

3. Run the deploy script to copy all source files and set code.py:
     python scripts/deploy.py examples/hw_test_demo.py
   The board reboots and starts running automatically.

Modes (press Button B to cycle)
--------------------------------
Mode 0 — RGB idle
    Five element effects (water, fire, lightning, earth, ice) fill each scope.
    Press A to step the brightness level from 1 → 10 → 1.

Mode 1 — IMU
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

import adafruit_is31fl3741
import board
import busio
import digitalio
from adafruit_is31fl3741.adafruit_rgbmatrixqt import Adafruit_RGBMatrixQT

from effects.render import PixelBuffer
from engine.effects.manager import EffectManager, EffectOutput
from engine.engine import GameEngine
from engine.input import ButtonData, InputEvents, MovementData
from engine.network import HardwareNetworkControls
from engine.packs import PackRegistry
from engine.scene import SceneManager
from engine.state import Scope
from scenes.hw_test.scene import factory as hw_test_factory

try:
    from typing import Final
except ImportError:
    pass

# ---------------------------------------------------------------------------
# Configuration — adjust to match your wiring
# ---------------------------------------------------------------------------

_MATRIX_COLS: "Final" = 13
_MATRIX_ROWS: "Final" = 9

BUTTON_A_PIN: "Final" = board.D9
BUTTON_B_PIN: "Final" = board.D10

# ---------------------------------------------------------------------------
# Hardware setup — IS31FL3741 LED matrix
# ---------------------------------------------------------------------------

i2c = busio.I2C(board.SCL, board.SDA)
while True:
    try:
        is31 = Adafruit_RGBMatrixQT(i2c, allocate=adafruit_is31fl3741.MUST_BUFFER)
        break
    except Exception:
        pass  # retry until matrix responds
is31.set_led_scaling(0x33)  # Brightness 0 → 0xFF
is31.global_current = 0xFF  # limit LED current for safe testing; raise for full brightness
is31.enable = True

# ---------------------------------------------------------------------------
# Hardware setup — buttons (pull-up: value=False when pressed)
# ---------------------------------------------------------------------------

_button_a = digitalio.DigitalInOut(BUTTON_A_PIN)
_button_a.switch_to_input(pull=digitalio.Pull.UP)
_button_b = digitalio.DigitalInOut(BUTTON_B_PIN)
_button_b.switch_to_input(pull=digitalio.Pull.UP)

_button_prev_a = True
_button_prev_b = True

# ---------------------------------------------------------------------------
# Hardware setup — IMU (optional, shares I2C bus with matrix)
# ---------------------------------------------------------------------------

_imu = None
try:
    import adafruit_lis3dh

    _imu = adafruit_lis3dh.LIS3DH_I2C(i2c)
except Exception:
    pass  # IMU absent; movement stays at zero

# ---------------------------------------------------------------------------
# Effect system
# ---------------------------------------------------------------------------


class IS31FL3741EffectOutput(EffectOutput):
    """EffectOutput that drives the IS31FL3741 13×9 RGB LED matrix.

    Mapping: frame ``f`` → matrix row ``f``; pixel ``p`` → matrix column ``p``.
    Unused rows are cleared to black each tick. ``is31.show()`` is called once
    after all rows are written.
    """

    def __init__(self) -> None:
        self.min_resolution = _MATRIX_COLS
        self.scopes = [Scope.ALL]

    def create_buffer(self) -> PixelBuffer:
        return PixelBuffer(_MATRIX_COLS)

    def update_pixels(self, frames: list) -> None:
        row_count = min(len(frames), _MATRIX_ROWS)

        for f in range(row_count):
            buf, _ = frames[f]
            for p in range(_MATRIX_COLS):
                is31.pixel(p, f, buf[p])

        for f in range(row_count, _MATRIX_ROWS):
            for p in range(_MATRIX_COLS):
                is31.pixel(p, f, 0)

    def show_pixels(self) -> None:
        is31.show()


_effect_registry = PackRegistry(item_attr="BUILD")
_effect_registry.scan_dir("packs/effects", "packs.effects")

_rule_registry = PackRegistry(item_attr="RULE")
_rule_registry.scan_dir("packs/rules", "packs.rules")

_effect_manager = EffectManager(
    registry=_effect_registry,
    outputs=[IS31FL3741EffectOutput()],
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

    # --- Read IMU ---
    if _imu is not None:
        try:
            _ax, _ay, _az = _imu.acceleration
        except Exception:
            _ax, _ay, _az = 0.0, 0.0, 0.0
    else:
        _ax, _ay, _az = 0.0, 0.0, 0.0

    # --- Queue combined input event ---
    if _manager._stack:
        _active_state = _manager._stack[-1][1]
        _active_state.queue_event(
            InputEvents.ButtonAndMovement(
                ButtonData(_btn_states),
                MovementData(_ax, _ay, _az),
            )
        )

    # --- Advance game rules ---
    _manager.update()

    # --- Advance effect rendering ---
    _effect_manager.update(_engine._timer)
