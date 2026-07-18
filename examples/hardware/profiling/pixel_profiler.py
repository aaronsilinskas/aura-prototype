"""CircuitPython pixel profiler — drives the real EffectManager -> EffectOutput
render+flush path to find the worst-case per-pixel and flush costs for the
``pixel_scope_costs`` table in `docs/hardware/recorded-metrics.md` (see also
`docs/hardware/calibration-guide.md`).

Sweeps three axes in sequence:

- **pixel count** — `PIXEL_COUNTS`, applied to the swept output's segment/row-band size.
- **effect identity** — cycles every registered element effect at a fixed level,
  to find the worst-case per-pixel cost across all real effects.
- **stack depth** — `STACK_DEPTHS`, the number of concurrent ``add_effect`` layers
  on the scope.

`DRIVER` selects which output is profiled:

- ``"neopixel_pwm"`` — a NeoPixel strip driven over PWM. Off the I2C bus.
- ``"is31fl3741_matrix"`` — an IS31FL3741 RGB matrix driven over I2C. Reports I2C
  bandwidth (`i2c_transaction_bytes * i2c_frequency_hz`) alongside CPU/heap stats.
  ``i2c_transaction_bytes`` is measured from one full render+flush tick at the
  worst-case (largest) pixel count — not guessed.

This profiler drives the satellite path (an `EffectManager` with one registered
`EffectOutput`, no rules) -- the same shape as `baseline_profiler.py`'s satellite
mode, but with a real pixel-producing output.

Hardware bring-up
-----------------
Hardware is brought up through a single `build_hardware` call from the **real**,
deployed `aura-device.json` (`load_device_config()`) -- the same config-driven model
`scene_load_profiler.py` established (#686) -- rather than an in-file, hand-built
`DeviceConfig`. The profiler drives exactly one pixel output, so every pixels-list
entry that isn't the profiled `DRIVER`'s entry is disabled on the parsed config (a
config declaring both a matrix and a NeoPixel strip has the other disabled), and
`config.isolate(keep="pixels")` (#715, #717) disables `audio`/`ir`/`accelerometer`/
`haptics`/`radio` if declared -- this profiler never drives them, so they are
isolated out rather than left to perturb the measurement as a fixed heap/I2C offset.
The **one** synthesized override layered on top of the loaded
config is the NeoPixel driver's swept max-length strip: the found strip entry's `count`
is bumped to the largest swept `PIXEL_COUNTS` value so every swept count addresses a
prefix of the same physical strip; everything else (pin, order, brightness,
scope_pixels, and for the matrix driver, `cols`) is the real prop's declared geometry,
never hand-built here.

`build_hardware` cannot be called in a loop -- it claims board pins without deiniting
them -- so the profiler builds once and sweeps `pixel_count` by constructing a fresh
production `EffectOutput` around the **one shared driver** the bundle already built,
pulled out via the read-only `matrix` / `strip` accessors. Each sweep wrapper is pure
software and claims no pins:

- **IS31FL3741 matrix:** per swept count, a new `IS31FL3741EffectOutput` whose `scope_rows`
  addresses that many rows (capped at the panel's `MATRIX_ROWS`) around the shared matrix.
  `MUST_BUFFER` makes `show()` write the full panel every flush, so flush cost is constant
  and only the per-pixel render cost scales -- the model holds exactly.
- **NeoPixel PWM:** the strip is built once at the largest swept count; per count a new
  `NeoPixelEffectOutput` addressing `range(0, pixel_count)` around that shared strip.
  `neopixel.show()` always clocks the full physical strip, so flush is a constant
  worst-case (max-length) figure rather than scaling with count -- an accepted, conservative
  approximation; the per-pixel render slope stays faithful.

If aura-device.json declares no pixel entry matching `DRIVER`, bring-up fails loud
(naming the missing kind) rather than reporting a zero-cost sweep -- the same rule
applies if the built bundle somehow comes back with no matching pixel output.

For the matrix driver, the board's default I2C bus is wrapped in `CountingI2C` and injected
into `build_hardware` (the `i2c=` seam), so `bytes_written` measured across one render+flush
tick gives the reported I2C bandwidth. NeoPixel PWM is off the I2C bus (bandwidth 0).

Hardware
--------
- ``"neopixel_pwm"``: a NeoPixel-compatible LED strip/ring, wired to the pin declared by
  the first NeoPixel entry in ``aura-device.json``.
- ``"is31fl3741_matrix"``: an IS31FL3741-based RGB matrix (e.g. Adafruit
  RGBMatrixQT) on the board's I2C bus.

Both modes read the profiler's button from ``buttons[0]`` in ``aura-device.json`` --
sourced from the real config's ``buttons`` list, which is not gated by ``enabled``.

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

import board

from effects.performance import PerformanceTracker
from engine.effects.manager import EffectManager
from engine.effects.output import EffectOutput
from engine.packs import PackRegistry
from engine.state import Scope
from engine.timer import Timer
from hardware.circuitpython.counting_i2c import CountingI2C
from hardware.circuitpython.device_builder import build_hardware, open_config_i2c
from hardware.circuitpython.is31fl3741_output import IS31FL3741EffectOutput
from hardware.circuitpython.neopixel_output import NeoPixelEffectOutput
from hardware.shared.device_config import (
    DeviceConfig,
    MatrixPixelsConfig,
    NeoPixelPixelsConfig,
    copy_with_enabled,
    load_device_config,
)
from hardware.shared.device_hardware import DeviceHardware
from hardware.shared.profiling_helpers import (
    linear_fit,
    print_profile_header,
    print_stats_line,
    print_table_row,
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

# The IS31FL3741 RGBMatrixQT is physically 13 columns by MATRIX_ROWS rows; a swept
# row band cannot address beyond it, so per-count row counts are capped here.
MATRIX_ROWS: Final = 9

# IS31FL3741 matrix driver constant -- used only when DRIVER == "is31fl3741_matrix".
# i2c_transaction_bytes is measured from one full update() tick (not declared here).
I2C_FREQUENCY_HZ: Final = TARGET_FPS


def _select_pixel_entry(
    config: DeviceConfig, driver: str, largest_count: int
) -> MatrixPixelsConfig | NeoPixelPixelsConfig:
    """Return the real pixel entry *driver* profiles, disabling every other one.

    Rebuilds *config*'s ``pixels`` list in place: every entry that isn't the profiled
    driver's own entry becomes a disabled copy (a config declaring both a matrix and a
    NeoPixel strip has the other disabled), and the target entry becomes an enabled
    copy -- entries are derived via `copy_with_enabled` rather than flipped in place,
    since `enabled` reads as an ordinary, construction-only field once parsed (#717).
    Isolating everything outside `pixels` (`audio`/`ir`/`accelerometer`/`haptics`/
    `radio`) is the caller's job via `config.isolate(keep="pixels")` -- `isolate`
    isolates one top-level component, not one entry among several sharing the
    `pixels` list, so picking among those stays this function's job.

    For the NeoPixel driver the found strip's ``count`` is overridden to *largest_count*
    -- the swept max-length strip, the one synthesized parameter this profiler layers on
    top of the loaded config. Everything else (pin, order, brightness, scope_pixels, and
    for the matrix driver, ``cols``) stays the real prop's declared geometry.

    Raises:
        ValueError: If *driver* names a pixel kind aura-device.json declares no entry
            for.
    """
    wanted = MatrixPixelsConfig if driver == "is31fl3741_matrix" else NeoPixelPixelsConfig
    target_index: int | None = None
    for i, entry in enumerate(config.pixels):
        is_candidate = isinstance(entry, wanted) and (wanted is MatrixPixelsConfig or entry.strips)
        if target_index is None and is_candidate:
            target_index = i
    if target_index is None:
        kind = "matrix" if driver == "is31fl3741_matrix" else "neopixel"
        raise ValueError(
            f"no {kind} pixels entry declared in aura-device.json for DRIVER={driver!r}"
        )

    target = copy_with_enabled(config.pixels[target_index], enabled=True)
    if isinstance(target, NeoPixelPixelsConfig):
        target.strips[0].count = largest_count

    config.pixels = [
        target if i == target_index else copy_with_enabled(entry, enabled=False)
        for i, entry in enumerate(config.pixels)
    ]
    return target


def _require_pixel_output(hardware: DeviceHardware, driver: str) -> EffectOutput:
    """Return the bundle's profiled pixel output, raising loudly if none is present.

    A missing output means the matrix or strip was not wired/reachable. Failing here
    keeps that from surfacing as a silent zero-cost sweep.
    """
    wanted = IS31FL3741EffectOutput if driver == "is31fl3741_matrix" else NeoPixelEffectOutput
    for output in hardware.outputs:
        if isinstance(output, wanted):
            return output
    raise RuntimeError(f"no {wanted.__name__} in the built hardware bundle -- pixel output missing")


def _build_sweep_output(
    driver: str, pixel_output: EffectOutput, pixel_count: int, matrix_cols: int
) -> tuple[EffectOutput, int]:
    """Build a fresh single-scope output for *pixel_count* around the shared driver.

    *matrix_cols* is the real matrix entry's declared ``cols`` (unused for the NeoPixel
    driver) -- the panel's physical column count comes from aura-device.json rather than
    a private constant, so it can never drift from the config actually built.

    Returns the output and the pixel count it actually addresses (the matrix row band
    is capped at the physical panel, so the effective count can be lower than requested).
    """
    if driver == "is31fl3741_matrix":
        rows = max(1, min((pixel_count + matrix_cols - 1) // matrix_cols, MATRIX_ROWS))
        output = IS31FL3741EffectOutput(
            pixel_output.matrix, cols=matrix_cols, scope_rows={"personal": range(0, rows)}
        )
        output.scopes = [Scope.PERSONAL]
        return output, rows * matrix_cols

    output = NeoPixelEffectOutput(pixel_output.strip, {"personal": range(0, pixel_count)})
    return output, pixel_count


def _measure_i2c_transaction_bytes(
    effect_manager: EffectManager,
    timer: Timer,
    element: str,
    counting_i2c: CountingI2C,
) -> int:
    """Return I2C bytes written across one full render+flush tick.

    Counts the whole ``update()`` tick (render + flush), not just ``show()``, so
    the figure captures all I2C traffic regardless of when the driver emits it.
    The production IS31FL3741 driver is buffered, so in practice every byte lands
    at ``show()``.
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
        perf.start_frame()
        perf.start_update_time()
        timer.update()
        effect_manager.update(timer)
        perf.add_update_time()

        if perf.complete_frame():
            print_stats_line(
                perf,
                pixel_count=pixel_count,
                element=element,
                stack_depth=stack_depth,
                i2c_bandwidth_bytes_per_sec=i2c_bandwidth,
            )

        if perf.last_frame_end > next_change_time:
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

    # Load the real, deployed aura-device.json and isolate the one component this
    # profiler drives -- the config-driven model #686 established for the scene-load
    # profiler. buttons[0] (not gated by `enabled`) is read straight off the same
    # config build_hardware below consumes -- no separate pin harvest.
    device_config = load_device_config()
    pixel_entry = _select_pixel_entry(device_config, DRIVER, PIXEL_COUNTS[-1])
    device_config = device_config.isolate(keep="pixels")
    matrix_cols = pixel_entry.cols if isinstance(pixel_entry, MatrixPixelsConfig) else 0

    # Build the device once: build_hardware claims pins without deiniting, so it cannot
    # be re-called per swept count. The one shared driver is reused across the sweep.
    counting_i2c = CountingI2C(open_config_i2c(device_config))
    hardware = build_hardware(device_config, board, i2c=counting_i2c)
    pixel_output = _require_pixel_output(hardware, DRIVER)

    # I2C bandwidth is a single constant worst-case figure, so measure it once up
    # front -- at the largest pixel count -- before the sweep. Measuring inside the
    # loop would leave every stats line 0.0 until the final pixel-count batch (and
    # entirely 0.0 if a long run is interrupted before reaching it). NeoPixel is off
    # the I2C bus, so its bandwidth stays 0.0.
    i2c_bandwidth = 0.0
    if DRIVER == "is31fl3741_matrix":
        worst_output, _ = _build_sweep_output(DRIVER, pixel_output, PIXEL_COUNTS[-1], matrix_cols)
        worst_manager = EffectManager(registry=registry, outputs=[worst_output])
        i2c_transaction_bytes = _measure_i2c_transaction_bytes(
            worst_manager, Timer(), element_names[0], counting_i2c
        )
        i2c_bandwidth = i2c_transaction_bytes * I2C_FREQUENCY_HZ
        worst_output = worst_manager = None
        gc.collect()

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
        output, actual_count = _build_sweep_output(DRIVER, pixel_output, pixel_count, matrix_cols)
        effect_manager = EffectManager(registry=registry, outputs=[output])
        timer = Timer()

        for element in element_names:
            for stack_depth in STACK_DEPTHS:
                update_ms = _measure_point(
                    effect_manager, timer, element, stack_depth, actual_count, i2c_bandwidth
                )
                samples[element].append((stack_depth * actual_count, update_ms))

        output = effect_manager = timer = None
        gc.collect()

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
