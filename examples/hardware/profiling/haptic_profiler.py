"""CircuitPython haptic profiler -- drives `Drv2605EffectOutput.handle_event` over
real I2C against a DRV2605L to find the per-event cost for the
`haptic_component_costs` table in `docs/hardware/recorded-metrics.md` (see also
`docs/hardware/calibration-guide.md`).

`Drv2605EffectOutput` is registered on `Scope.ALL` -- there is exactly one shared
haptic component per prop (one DRV2605L haptic driver), so this profiler drives it
directly.

Each iteration:

1. Calls `handle_event` with a short haptic pattern -- this writes the sequence to
   the DRV2605L over I2C and calls `driver.play()`.
2. Calls `flush()` -- a no-op unless the receipt was externally stopped.
3. Sleeps for `EVENT_INTERVAL_SECONDS` between events, at a low event rate -- the I2C
   bus share is negligible but still counted.

`PerformanceTracker` reports the per-event `handle_event` cost (the `cost_ms` term)
alongside the uniform stats line.

Hardware bring-up
-----------------
The driver is brought up through a single `build_hardware` call from the **real**,
deployed `aura-device.json` (`load_device_config()`) -- the config-driven model #686
established for the scene-load profiler -- rather than an in-file, hand-built minimal
`DeviceConfig`. This profiler drives the DRV2605L and nothing else, so every declared
`pixels` entry plus `audio`/`ir`/`accelerometer` (if present) is set `enabled = False` on
the parsed config; `haptics` is force-enabled the same way. A config declaring no
`haptics` section at all fails loudly here -- there is no minimal stand-in section to
fall back on, since the real driver is what this profiler measures (the #691 stop-gap
`haptics={}` in-file section is gone). If the DRV2605L isn't wired/reachable,
`build_hardware` itself raises (a declared-but-unreachable component is a hard error, not
a silent omission), so bring-up still fails loud rather than reporting a zero-cost
measurement.

The board's default I2C bus is wrapped in `CountingI2C` and injected into
`build_hardware` (the `i2c=` seam), so every peripheral shares the counted bus. The
decorator is reset before a representative haptic event and `bytes_written` after that
event gives the measured `i2c_transaction_bytes` -- no guessing required.

Hardware
--------
- DRV2605L haptic driver on the board's default I2C bus (SDA/SCL), wired per the
  real, deployed `aura-device.json`'s `haptics` section.

Installation
------------
1. Install CircuitPython on your board:
   https://learn.adafruit.com/welcome-to-circuitpython/installing-circuitpython

2. Run the deploy script to copy all source files and set code.py:
     python scripts/deploy.py examples/hardware/profiling/haptic_profiler.py
   The board reboots and starts running automatically.

Configuration
-------------
- EVENT_INTERVAL_SECONDS: delay between events -- sets the event rate
  (e.g. 10.0s -> 6 calls/minute)
- ITERATIONS: number of haptic events to drive before exiting
- TARGET_FPS: informational only -- included in the header for comparison against
  other profilers
- LOG_INTERVAL_SECONDS: how often the stats line is printed
"""

from __future__ import annotations

import time

import board

from effects.effect import Effect, EffectHaptic, HapticPattern
from effects.performance import PerformanceTracker
from engine.events import EffectEvent
from engine.state import EffectReceipt
from hardware.circuitpython.counting_i2c import CountingI2C
from hardware.circuitpython.device_builder import build_hardware
from hardware.circuitpython.drv2605_output import Drv2605EffectOutput
from hardware.shared.device_config import DeviceConfig, load_device_config
from hardware.shared.device_hardware import DeviceHardware
from hardware.shared.profiling_helpers import (
    mute_other_components,
    open_config_i2c,
    print_profile_header,
    print_stats_line,
    print_table_row,
)

try:
    from typing import Final
except ImportError:
    pass

EVENT_INTERVAL_SECONDS: Final = 10.0  # 6 calls/minute
ITERATIONS: Final = 12
TARGET_FPS: Final = 24.0
LOG_INTERVAL_SECONDS: Final = 5.0

_EVENT_VERB: Final = "buzz"


def _require_drv2605_output(hardware: DeviceHardware) -> Drv2605EffectOutput:
    """Return the bundle's `Drv2605EffectOutput`, raising loudly if none is present.

    `build_hardware` itself raises if a declared `haptics` section's driver can't be
    constructed, so this only guards against a caller mistake -- e.g. `run()`'s config
    ending up without a `haptics` section -- rather than a normal "not present" case.
    """
    for output in hardware.outputs:
        if isinstance(output, Drv2605EffectOutput):
            return output
    raise RuntimeError("no Drv2605EffectOutput in the built hardware bundle -- no DRV2605 found")


def _isolate_haptics_config(config: DeviceConfig) -> None:
    """Mute every component but `haptics` on *config*, in place.

    This profiler drives the DRV2605L and nothing else, so everything but `haptics`
    is muted via `mute_other_components` -- the non-destructive isolation knob
    alongside dropping a section from aura-device.json outright. `haptics` itself is
    force-enabled: it is the real driver section this profiler exists to exercise, so
    a config that merely declared it disabled would otherwise silently defeat the
    measurement.

    Raises:
        ValueError: If *config* declares no `haptics` section at all -- there is no
            minimal stand-in section to fall back on (the #691 `haptics={}` stop-gap
            is gone); the real prop must declare its haptics driver.
    """
    if config.haptics is None:
        raise ValueError(
            "haptics not declared in aura-device.json -- the haptic profiler measures"
            + " the real driver, not a synthesized stand-in"
        )
    config.haptics.enabled = True
    mute_other_components(config, keep="haptics")


def run() -> None:
    """Drive `handle_event` once per `EVENT_INTERVAL_SECONDS`, reporting per-event cost."""
    device_config = load_device_config()
    _isolate_haptics_config(device_config)

    # Source the I2C bus pins from the real aura-device.json so the injected
    # (byte-counting) bus lands on the configured SDA/SCL.
    counting_bus = CountingI2C(open_config_i2c(device_config))
    hardware = build_hardware(device_config, board, i2c=counting_bus)
    output = _require_drv2605_output(hardware)

    buzz_effect = Effect(
        "profiler.buzz",
        haptic=EffectHaptic({_EVENT_VERB: HapticPattern([HapticPattern.STRONG_CLICK])}),
    )
    buzz_event = EffectEvent("profiler", "buzz", _EVENT_VERB)

    perf = PerformanceTracker(log_interval=LOG_INTERVAL_SECONDS)
    max_calls_per_minute = 60.0 / EVENT_INTERVAL_SECONDS

    print_profile_header(
        component="haptic",
        sweep_axes=["max_calls_per_minute"],
        sweep_values=[max_calls_per_minute],
        target_fps=TARGET_FPS,
    )

    counting_bus.reset()
    receipt = EffectReceipt(0)
    output.handle_event(buzz_event, frozenset({"all"}), buzz_effect, receipt)
    output.flush()
    i2c_transaction_bytes = counting_bus.bytes_written

    for _ in range(ITERATIONS):
        perf.start_frame()
        perf.start_update_time()
        receipt = EffectReceipt(0)
        output.handle_event(buzz_event, frozenset({"all"}), buzz_effect, receipt)
        output.flush()
        perf.add_update_time()

        if perf.complete_frame():
            print_stats_line(
                perf,
                max_calls_per_minute=max_calls_per_minute,
            )

        time.sleep(EVENT_INTERVAL_SECONDS)

    cost_ms = perf.update_time_total / perf.frame_count * 1000.0
    i2c_bandwidth = i2c_transaction_bytes * (max_calls_per_minute / 60.0)
    print_table_row(
        "haptic_component_costs",
        [f"{cost_ms:.4f}", f"{i2c_bandwidth:.2f}"],
    )


run()
