"""CircuitPython hardware demo — RP2040 PropMaker + IS31FL3741 13×9 LED matrix.

A fire effect is hardcoded at startup and rendered across the LED matrix.
Subsequent issues add button input (#34), audio output (#35), and FPS
reporting (#36).

Hardware
--------
- Adafruit RP2040 PropMaker Feather
- Adafruit IS31FL3741 13×9 RGB LED Matrix Breakout (I2C on default SDA/SCL)

Installation
------------
1. Install CircuitPython on your PropMaker board:
   https://learn.adafruit.com/adafruit-feather-rp2040-prop-maker

2. Copy the following libraries to CIRCUITPY/lib/:
     adafruit_is31fl3741/

3. Copy the effects/ and engine/ directories to the CIRCUITPY drive root so
   they live at /CIRCUITPY/effects/ and /CIRCUITPY/engine/.

4. Copy this file to /CIRCUITPY/code.py.
   The board reboots and starts running automatically.

Configuration
-------------
- TARGET_FPS: animation update rate (default 20)
"""

import time

import board
import busio
from adafruit_is31fl3741.adafruit_rgbmatrixqt import Adafruit_RGBMatrixQT

from effects.elements.registry import build_element_renderer
from effects.manager.manager import EffectBuilder, EffectManager, EffectOutput
from effects.manager.scope import Scope
from effects.render import EffectRenderer, PixelBuffer, RendererConfig
from engine.timer import Timer

try:
    from typing import Final
except ImportError:
    pass

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

TARGET_FPS: "Final" = 20
_TICK_SECONDS: "Final" = 1.0 / TARGET_FPS

_MATRIX_COLS: "Final" = 13
_MATRIX_ROWS: "Final" = 9

# ---------------------------------------------------------------------------
# Hardware setup
# ---------------------------------------------------------------------------

i2c = busio.I2C(board.SCL, board.SDA)
time.sleep(3)  # Wait for RGB panel to initialize.
is31 = Adafruit_RGBMatrixQT(i2c)
is31.global_current = 0x0A  # limit LED current for safe testing; raise for full brightness
is31.enable = True

# ---------------------------------------------------------------------------
# Effect system
# ---------------------------------------------------------------------------


class ElementEffectBuilder(EffectBuilder):
    def __call__(self, name: str, config: RendererConfig) -> EffectRenderer:
        return build_element_renderer(name, config)


class IS31FL3741EffectOutput(EffectOutput):
    """EffectOutput that drives the IS31FL3741 13×9 RGB LED matrix.

    Mapping: frame ``f`` → matrix row ``f``; pixel ``p`` → matrix column ``p``.
    Unused rows are cleared to black each tick. ``is31.show()`` is called once
    after all rows are written.
    """

    def __init__(self) -> None:
        self.min_resolution = _MATRIX_COLS
        self.scopes = [Scope.PERSONAL]

    def create_buffer(self) -> PixelBuffer:
        return PixelBuffer(_MATRIX_COLS)

    def update_pixels(self, frames: list) -> None:
        row_count = min(len(frames), _MATRIX_ROWS)

        # Write active frames to their matrix rows
        for f in range(row_count):
            buf = frames[f]
            for p in range(_MATRIX_COLS):
                is31.pixel(p, f, buf[p])  # pixel(x, y, packed_24bit_color)

        # Clear unused rows to black
        for f in range(row_count, _MATRIX_ROWS):
            for p in range(_MATRIX_COLS):
                is31.pixel(p, f, 0)

        is31.show()


effect_output = IS31FL3741EffectOutput()
effect_manager = EffectManager(
    builder=ElementEffectBuilder(),
    outputs=[effect_output],
)

# Hardcode a fire effect for Phase 1 (Issue #33).
# Button input to layer / clear effects is added in Issue #34.
effect_manager.set_effect(Scope.PERSONAL, "fire", 5, {})

# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

timer = Timer()
while True:
    timer.update()
    effect_manager.update(timer)
    time.sleep(_TICK_SECONDS)
