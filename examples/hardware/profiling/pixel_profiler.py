"""CircuitPython pixel profiler — drives the real EffectManager -> EffectOutput
render+flush path to find the worst-case per-pixel and flush costs for the capacity
estimator's pixel model (see `docs/hardware/capacity-model.md` and #396).

Sweeps three axes in sequence:

- **pixel count** — `PIXEL_COUNTS`, applied to the active output's strip/matrix size.
- **effect identity** — cycles every registered element effect (as
  ``element_perf_demo.py`` does) at a fixed level, to find the worst-case
  per-pixel cost across all real effects.
- **stack depth** — `STACK_DEPTHS`, the number of concurrent ``add_effect`` layers
  on the scope (mirrors the estimator's `stack_depth` workload parameter).

`DRIVER` selects which output is profiled:

- ``"neopixel_pwm"`` — a NeoPixel strip driven over PWM. Off the I2C bus.
- ``"is31fl3741_matrix"`` — an IS31FL3741 RGB matrix driven over I2C. Reports I2C
  bandwidth (`transaction_size * frequency`) alongside CPU/heap stats.

This profiler drives the satellite path (an `EffectManager` with one registered
`EffectOutput`, no rules) -- the same shape as `baseline_profiler.py`'s satellite
mode, but with a real pixel-producing output.

Hardware
--------
- ``"neopixel_pwm"``: a NeoPixel-compatible LED strip/ring on `NEOPIXEL_PIN`.
- ``"is31fl3741_matrix"``: an IS31FL3741-based RGB matrix (e.g. Adafruit
  RGBMatrixQT) on the board's I2C bus.

Installation
------------
1. Install CircuitPython on your board:
   https://learn.adafruit.com/welcome-to-circuitpython/installing-circuitpython

2. Run the deploy script to copy all source files and set code.py:
     python scripts/deploy.py examples/hardware/profiling/pixel_profiler.py
   The board reboots and starts running automatically.

Configuration
-------------
- DRIVER: "neopixel_pwm" or "is31fl3741_matrix"
- PIXEL_COUNTS: pixel counts to sweep, in order
- STACK_DEPTHS: stack depths (concurrent add_effect layers) to sweep, in order
- SAMPLE_LEVEL: effect intensity level used for every effect in the cycle
- TARGET_FPS: informational only -- included in the header for comparison
  against other profilers
- DISPLAY_SECONDS: how long to spend on each (pixel_count, effect, stack_depth)
  combination before advancing
- LOG_INTERVAL_SECONDS: how often the stats line is printed
- I2C_TRANSACTION_BYTES / I2C_FREQUENCY_HZ: matrix-driver constants used to report
  `i2c_bandwidth_bytes_per_sec = transaction_size * frequency`
"""

from __future__ import annotations

import gc
import time

from effects.effect import PixelBuffer
from effects.performance import PerformanceTracker
from engine.effects.manager import EffectManager, EffectOutput
from engine.packs import PackRegistry
from engine.state import Scope
from engine.timer import Timer
from hardware.shared.matrix_output import MatrixEffectOutput
from hardware.shared.profiling_helpers import (
    print_profile_header,
    print_stats_line,
    stats_due,
)

try:
    from typing import Final
except ImportError:
    pass

DRIVER: Final = "neopixel_pwm"  # or "is31fl3741_matrix"
PIXEL_COUNTS: Final = [10, 50, 150]
STACK_DEPTHS: Final = [1, 2, 4]
SAMPLE_LEVEL: Final = 7
TARGET_FPS: Final = 24.0
DISPLAY_SECONDS: Final = 10.0
LOG_INTERVAL_SECONDS: Final = 5.0

# IS31FL3741 matrix driver constants -- used only when DRIVER == "is31fl3741_matrix".
I2C_TRANSACTION_BYTES: Final = 200
I2C_FREQUENCY_HZ: Final = TARGET_FPS


class NeoPixelPwmOutput(EffectOutput):
    """Satellite output for a NeoPixel strip driven over PWM.

    Buffers one frame per scope key and writes it to the underlying `neopixel`
    object on ``flush``. Off the I2C bus -- ``i2c_bandwidth_bytes_per_sec`` is 0
    for this driver.
    """

    def __init__(self, pixel_count: int, strip) -> None:
        super().__init__(receives_pixels=True)
        self.min_resolution = pixel_count
        self.scopes = [Scope.PERSONAL]
        self._pixel_count = pixel_count
        self._strip = strip

    def create_buffer(self, scope_key: str) -> PixelBuffer:
        return PixelBuffer(self._pixel_count)

    def update_pixels(self, scope_key: str, buffers: list, receipts: list) -> None:
        if not buffers:
            return
        buf = buffers[-1]
        for i in range(self._pixel_count):
            self._strip[i] = buf[i]

    def clear_pixels(self, scope_key: str) -> None:
        for i in range(self._pixel_count):
            self._strip[i] = 0

    def flush(self) -> None:
        self._strip.show()


class Is31fl3741MatrixOutput(MatrixEffectOutput):
    """Satellite output for an IS31FL3741 matrix driven over I2C.

    Subclasses ``MatrixEffectOutput`` (shared scope-to-row-band routing) and routes
    `Scope.PERSONAL` to every row of the matrix so the profiler can sweep
    `pixel_count` against `_cols`. ``flush`` calls the underlying matrix's
    ``show()``, the dominant I2C consumer.
    """

    def __init__(self, cols: int, rows: int, matrix) -> None:
        super().__init__(cols, {"personal": range(rows)})
        self.scopes = [Scope.PERSONAL]
        self._matrix = matrix

    def _write_row(self, row: int, pixels) -> None:
        for col in range(self._cols):
            self._matrix.pixel(col, row, pixels[col])

    def flush(self) -> None:
        self._matrix.show()


def _build_neopixel_output(pixel_count: int) -> EffectOutput:
    import board
    import neopixel

    strip = neopixel.NeoPixel(pin=board.D5, n=pixel_count, brightness=0.5, auto_write=False)
    return NeoPixelPwmOutput(pixel_count, strip)


def _build_matrix_output(pixel_count: int) -> EffectOutput:
    import board
    import busio
    from adafruit_is31fl3741.adafruit_rgbmatrixqt import Adafruit_RGBMatrixQT

    i2c = busio.I2C(board.SCL, board.SDA)
    matrix = Adafruit_RGBMatrixQT(i2c)
    cols = 13
    rows = max(1, (pixel_count + cols - 1) // cols)
    return Is31fl3741MatrixOutput(cols, rows, matrix)


def _build_output(driver: str, pixel_count: int) -> EffectOutput:
    if driver == "neopixel_pwm":
        return _build_neopixel_output(pixel_count)
    if driver == "is31fl3741_matrix":
        return _build_matrix_output(pixel_count)
    raise ValueError(f"Unknown DRIVER: {driver!r}")


def run() -> None:
    """Sweep pixel count, effect identity, and stack depth for `DRIVER`."""
    registry = PackRegistry(item_attr="BUILD")
    registry.scan_dir("packs/effects", "packs.effects")
    element_names = registry.items("elements")

    i2c_bandwidth = I2C_TRANSACTION_BYTES * I2C_FREQUENCY_HZ if DRIVER == "is31fl3741_matrix" else 0

    for pixel_count in PIXEL_COUNTS:
        output = _build_output(DRIVER, pixel_count)
        effect_manager = EffectManager(registry=registry, outputs=[output])
        timer = Timer()
        perf = PerformanceTracker(log_interval=LOG_INTERVAL_SECONDS)

        print_profile_header(
            component=f"pixel.{DRIVER}",
            sweep_axes=["pixel_count", "element", "stack_depth"],
            sweep_values=[pixel_count, element_names[0], STACK_DEPTHS[0]],
            target_fps=TARGET_FPS,
        )

        for element in element_names:
            for stack_depth in STACK_DEPTHS:
                receipts = []
                for _ in range(stack_depth):
                    receipt = effect_manager.add_effect(
                        Scope.PERSONAL,
                        "elements." + element,
                        {"level": SAMPLE_LEVEL},
                    )
                    receipts.append(receipt)

                next_change_time = time.monotonic() + DISPLAY_SECONDS
                while True:
                    current_time = time.monotonic()

                    perf.start_frame()
                    perf.start_update_time()
                    timer.update()
                    effect_manager.update(timer)
                    perf.add_update_time()

                    due = stats_due(perf, current_time)
                    perf.complete_frame(current_time)
                    if due:
                        extra = {
                            "pixel_count": pixel_count,
                            "element": element,
                            "stack_depth": stack_depth,
                            "i2c_bandwidth_bytes_per_sec": i2c_bandwidth,
                        }
                        print_stats_line(perf, current_time, **extra)

                    if current_time > next_change_time:
                        break

                for receipt in receipts:
                    receipt.stop()
                gc.collect()


run()
