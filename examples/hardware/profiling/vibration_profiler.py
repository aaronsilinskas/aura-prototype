"""CircuitPython vibration profiler -- drives `Drv2605EffectOutput.handle_event` over
real I2C against a DRV2605L to find the per-event cost for the capacity estimator's
`VibrationComponent` model (see `docs/hardware/capacity-model.md` and #398).

`Drv2605EffectOutput` is registered on `Scope.ALL` -- there is exactly one shared
vibration component per prop (one DRV2605L haptic motor), so this profiler drives it
directly.

Each iteration:

1. Calls `handle_event` with a short vibration pattern -- this writes the sequence to
   the DRV2605L over I2C and calls `motor.play()`.
2. Calls `flush()` -- a no-op unless the receipt was externally stopped.
3. Sleeps for `EVENT_INTERVAL_SECONDS` between events, modeling
   `max_calls_per_minute` (a low event rate -- the I2C bus share is negligible but
   still counted, per #398).

`PerformanceTracker` reports the per-event `handle_event` cost (the
`VibrationComponent.cost_ms` term) alongside the uniform stats line.

Hardware
--------
- DRV2605L haptic motor driver on the board's default I2C bus (SDA/SCL).

Installation
------------
1. Install CircuitPython on your board:
   https://learn.adafruit.com/welcome-to-circuitpython/installing-circuitpython

2. Run the deploy script to copy all source files and set code.py:
     python scripts/deploy.py examples/hardware/profiling/vibration_profiler.py
   The board reboots and starts running automatically.

Configuration
-------------
- EVENT_INTERVAL_SECONDS: delay between events -- models `max_calls_per_minute`
  (e.g. 10.0s -> 6 calls/minute)
- ITERATIONS: number of vibration events to drive before exiting
- TARGET_FPS: informational only -- included in the header for comparison against
  other profilers
- LOG_INTERVAL_SECONDS: how often the stats line is printed
"""

from __future__ import annotations

import time

from effects.effect import Effect, EffectVibration, VibrationConfig
from effects.performance import PerformanceTracker
from engine.events import EffectEvent
from engine.state import EffectReceipt
from hardware.shared.profiling_helpers import (
    print_profile_header,
    print_stats_line,
    print_table_row,
    stats_due,
)

try:
    from typing import Final
except ImportError:
    pass

EVENT_INTERVAL_SECONDS: Final = 10.0  # 6 calls/minute
ITERATIONS: Final = 12
TARGET_FPS: Final = 24.0
LOG_INTERVAL_SECONDS: Final = 5.0
# Bytes the DRV2605L sequence + go-register write puts on the I2C bus per event.
# A configured seed (like the pixel matrix's I2C_TRANSACTION_BYTES), not measured
# here -- refine via an I2C bus capture if a tighter figure is needed.
I2C_TRANSACTION_BYTES: Final = 8

_EVENT_VERB: Final = "buzz"


def _build_output():
    import board
    import busio

    from hardware.circuitpython.drv2605_output import Drv2605EffectOutput
    from hardware.circuitpython.propmaker import setup_drv2605

    i2c = busio.I2C(board.SCL, board.SDA)
    motor = setup_drv2605(i2c)
    return Drv2605EffectOutput(motor)


def run() -> None:
    """Drive `handle_event` once per `EVENT_INTERVAL_SECONDS`, reporting per-event cost."""
    output = _build_output()

    buzz_effect = Effect(
        "profiler.buzz",
        vibration=EffectVibration({_EVENT_VERB: VibrationConfig([VibrationConfig.STRONG_CLICK])}),
    )
    buzz_event = EffectEvent("profiler", "buzz", _EVENT_VERB)

    perf = PerformanceTracker(log_interval=LOG_INTERVAL_SECONDS)
    max_calls_per_minute = 60.0 / EVENT_INTERVAL_SECONDS

    print_profile_header(
        component="vibration",
        sweep_axes=["max_calls_per_minute"],
        sweep_values=[max_calls_per_minute],
        target_fps=TARGET_FPS,
    )

    for _ in range(ITERATIONS):
        current_time = time.monotonic()

        perf.start_frame()
        perf.start_update_time()
        receipt = EffectReceipt(0)
        output.handle_event(buzz_event, frozenset({"all"}), buzz_effect, receipt)
        output.flush()
        perf.add_update_time()

        due = stats_due(perf, current_time)
        perf.complete_frame(current_time)
        if due:
            print_stats_line(
                perf,
                current_time,
                max_calls_per_minute=max_calls_per_minute,
            )

        time.sleep(EVENT_INTERVAL_SECONDS)

    cost_ms = perf.update_time_total / perf.frame_count * 1000.0
    i2c_bandwidth = I2C_TRANSACTION_BYTES * (max_calls_per_minute / 60.0)
    print_table_row(
        "vibration_component_costs",
        [f"{cost_ms:.4f}", f"{i2c_bandwidth:.2f}"],
    )


run()
