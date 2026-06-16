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
  bandwidth (`i2c_transaction_bytes * i2c_frequency_hz`) alongside CPU/heap stats.
  ``i2c_transaction_bytes`` is measured from one full render+flush tick at the
  worst-case (largest) pixel count — not guessed.

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
- I2C_FREQUENCY_HZ: matrix-driver frequency term used to report
  `i2c_bandwidth_bytes_per_sec = i2c_transaction_bytes * i2c_frequency_hz`
  (i2c_transaction_bytes is measured, not declared)
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
from hardware.circuitpython.counting_i2c import CountingI2C
from hardware.shared.matrix_output import MatrixEffectOutput
from hardware.shared.profiling_helpers import (
    linear_fit,
    print_profile_header,
    print_stats_line,
    print_table_row,
    stats_due,
)

try:
    from typing import Final
except ImportError:
    pass

DRIVER: Final = "is31fl3741_matrix"  # or "neopixel_pwm"
PIXEL_COUNTS: Final = [10, 50, 150]
STACK_DEPTHS: Final = [1, 2, 4]
SAMPLE_LEVEL: Final = 7
TARGET_FPS: Final = 24.0
DISPLAY_SECONDS: Final = 10.0
LOG_INTERVAL_SECONDS: Final = 5.0

# IS31FL3741 matrix driver constant -- used only when DRIVER == "is31fl3741_matrix".
# i2c_transaction_bytes is measured from one full update() tick (not declared here).
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

    def deinit(self) -> None:
        self._strip.deinit()


class Is31fl3741MatrixOutput(MatrixEffectOutput):
    """Satellite output for an IS31FL3741 matrix driven over I2C.

    Subclasses ``MatrixEffectOutput`` (shared scope-to-row-band routing) and routes
    `Scope.PERSONAL` to every row of the matrix so the profiler can sweep
    `pixel_count` against `_cols`. ``flush`` calls the underlying matrix's
    ``show()``, the dominant I2C consumer.
    """

    def __init__(self, cols: int, rows: int, matrix, counting_i2c: CountingI2C) -> None:
        super().__init__(cols, {"personal": range(rows)})
        self.scopes = [Scope.PERSONAL]
        self._matrix = matrix
        self._counting_i2c = counting_i2c

    def _write_row(self, row: int, pixels) -> None:
        for col in range(self._cols):
            self._matrix.pixel(col, row, pixels[col])

    def flush(self) -> None:
        self._matrix.show()

    def deinit(self) -> None:
        self._counting_i2c.deinit()


def _build_neopixel_output(pixel_count: int) -> NeoPixelPwmOutput | Is31fl3741MatrixOutput:
    import board
    import neopixel

    strip = neopixel.NeoPixel(pin=board.D5, n=pixel_count, brightness=0.5, auto_write=False)
    return NeoPixelPwmOutput(pixel_count, strip)


def _build_matrix_output(
    pixel_count: int,
) -> tuple[Is31fl3741MatrixOutput, CountingI2C]:
    import board
    import busio

    import hardware.circuitpython.propmaker as propmaker

    i2c = busio.I2C(board.SCL, board.SDA)
    counting_i2c = CountingI2C(i2c)
    matrix = propmaker.setup_matrix_is31fl3741(counting_i2c)
    cols = 13
    rows = max(1, (pixel_count + cols - 1) // cols)
    return Is31fl3741MatrixOutput(cols, rows, matrix, counting_i2c), counting_i2c


def _build_output(
    driver: str, pixel_count: int
) -> tuple[NeoPixelPwmOutput | Is31fl3741MatrixOutput, CountingI2C | None]:
    if driver == "neopixel_pwm":
        return _build_neopixel_output(pixel_count), None
    if driver == "is31fl3741_matrix":
        return _build_matrix_output(pixel_count)
    raise ValueError(f"Unknown DRIVER: {driver!r}")


def _measure_i2c_transaction_bytes(
    effect_manager: EffectManager,
    timer: Timer,
    element: str,
    counting_i2c: CountingI2C,
) -> int:
    """Return I2C bytes written across one full render+flush tick.

    Counts the whole ``update()`` tick, not just ``show()``: a no-buffer driver
    emits bytes per pixel during the render pass, so a ``show()``-only count
    would miss all traffic.
    """
    receipt = effect_manager.add_effect(
        Scope.PERSONAL, "elements." + element, {"level": SAMPLE_LEVEL}
    )
    timer.update()
    effect_manager.update(timer)  # warm-up tick — discard
    counting_i2c.reset()
    timer.update()
    effect_manager.update(timer)  # measured tick
    i2c_transaction_bytes = counting_i2c.bytes_written
    receipt.stop()
    return i2c_transaction_bytes


def _measure_point(
    effect_manager: EffectManager,
    timer: Timer,
    element: str,
    stack_depth: int,
    pixel_count: int,
    i2c_bandwidth: float,
) -> float:
    """Run one steady-state point and return its average per-frame cost (ms).

    `effect_manager.update` renders every active layer and flushes the output,
    so the returned average is the full per-frame render+flush cost the pixel
    scope cost model charges. Reports the uniform stats line each interval.
    """
    receipts = []
    for _ in range(stack_depth):
        receipt = effect_manager.add_effect(
            Scope.PERSONAL,
            "elements." + element,
            {"level": SAMPLE_LEVEL},
        )
        receipts.append(receipt)

    perf = PerformanceTracker(log_interval=LOG_INTERVAL_SECONDS)
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
            print_stats_line(
                perf,
                current_time,
                pixel_count=pixel_count,
                element=element,
                stack_depth=stack_depth,
                i2c_bandwidth_bytes_per_sec=i2c_bandwidth,
            )

        if current_time > next_change_time:
            break

    for receipt in receipts:
        receipt.stop()
    gc.collect()
    return perf.update_time_total / perf.frame_count * 1000.0


def run() -> None:
    """Sweep pixel count, effect identity, and stack depth for `DRIVER`."""
    registry = PackRegistry(item_attr="BUILD")
    registry.scan_dir("packs/effects", "packs.effects")
    element_names = registry.items("elements")

    # For the matrix driver, measure i2c_transaction_bytes at the largest
    # (worst-case) pixel count so the bandwidth figure is conservative.
    worst_pixel_count = PIXEL_COUNTS[-1]
    i2c_bandwidth = 0.0
    counting_i2c = None

    print_profile_header(
        component=f"pixel.{DRIVER}",
        sweep_axes=["pixel_count", "element", "stack_depth"],
        sweep_values=[PIXEL_COUNTS[0], element_names[0], STACK_DEPTHS[0]],
        target_fps=TARGET_FPS,
    )

    # cost_ms = stack_depth * worst_case_effect_per_pixel_ms * pixel_count + flush_ms,
    # so per-frame cost is linear in (stack_depth * pixel_count): the slope is the
    # per-pixel-per-layer cost and the intercept is the fixed flush. Collect points
    # per element so the worst-case element's slope can be selected.
    samples = {element: [] for element in element_names}
    for pixel_count in PIXEL_COUNTS:
        output, counting_i2c = _build_output(DRIVER, pixel_count)
        effect_manager = EffectManager(registry=registry, outputs=[output])
        timer = Timer()

        # Measure I2C transaction bytes once at the largest pixel count.
        if DRIVER == "is31fl3741_matrix" and pixel_count == worst_pixel_count:
            i2c_transaction_bytes = _measure_i2c_transaction_bytes(
                effect_manager, timer, element_names[0], counting_i2c
            )
            i2c_bandwidth = i2c_transaction_bytes * I2C_FREQUENCY_HZ

        for element in element_names:
            for stack_depth in STACK_DEPTHS:
                update_ms = _measure_point(
                    effect_manager, timer, element, stack_depth, pixel_count, i2c_bandwidth
                )
                samples[element].append((stack_depth * pixel_count, update_ms))
        output.deinit()

    # Worst-case element drives worst_case_effect_per_pixel_ms; its fit's intercept
    # is the matching flush_ms (flush is element-independent in the model).
    worst_per_pixel_ms = 0.0
    flush_ms = 0.0
    for points in samples.values():
        xs = [x for x, _ in points]
        ys = [y for _, y in points]
        slope, intercept = linear_fit(xs, ys)
        if slope > worst_per_pixel_ms:
            worst_per_pixel_ms = slope
            flush_ms = intercept

    print_table_row(
        "pixel_scope_costs",
        [f"{worst_per_pixel_ms:.6f}", f"{flush_ms:.4f}", i2c_bandwidth],
        driver=DRIVER,
    )


run()
