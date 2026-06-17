"""CircuitPython IR-transmit profiler -- drives `InfraredTransmitter.send` /
`HardwareNetworkControls.send_ir` over a real `pulseio.PulseOut`, measuring the
blocking duration of `PulseOut.send` vs payload length for the capacity estimator's
`IrTransmitComponent` model (see `docs/hardware/capacity-model.md` and #398).

`HardwareNetworkControls.send_ir` selects 1 of up to 3 wired
`InfraredTransmitter` instances (LINE / CONE / AREA_OF_EFFECT) per send -- there is
exactly one shared IR-transmit component per prop (the emitters add no parallel
cost), so this profiler drives the LINE transmitter directly.

Sweeps one axis:

- **payload length** -- `PAYLOAD_LENGTHS`, the number of bytes encoded and
  transmitted per `send_ir` call. Longer payloads produce more pulses, increasing
  `PulseOut.send`'s blocking duration -- the *soft* real-time cost
  (`blocking_send_ms`) that contributes to a co-located receiver's worst-case frame
  time (#398).

For each payload length, the profiler times `send_ir` directly with
`time.monotonic()` (the call blocks for the whole pulse train, so
`PerformanceTracker`'s per-frame update-time captures it) and reports the blocking
duration alongside the uniform stats line.

Hardware
--------
- IR emitter (LINE) wired to `LINE_PIN`, driven via `pulseio.PulseOut` at 38kHz
  (see `propmaker.setup_ir`).

Installation
------------
1. Install CircuitPython on your board:
   https://learn.adafruit.com/welcome-to-circuitpython/installing-circuitpython

2. Run the deploy script to copy all source files and set code.py:
     python scripts/deploy.py examples/hardware/profiling/ir_tx_profiler.py
   The board reboots and starts running automatically.

Configuration
-------------
- LINE_PIN: board pin for the LINE emitter's `pulseio.PulseOut`
- RX_PIN: board pin for the (unused but required by `setup_ir`) IR receiver
- PAYLOAD_LENGTHS: payload byte-lengths to sweep, in order
- ITERATIONS_PER_LENGTH: number of `send_ir` calls per payload length
- TARGET_FPS: informational only -- included in the header for comparison against
  other profilers
- LOG_INTERVAL_SECONDS: how often the stats line is printed
"""

from __future__ import annotations

import time

from effects.performance import PerformanceTracker
from engine.network import LINE, HardwareNetworkControls
from hardware.shared.profiling_helpers import (
    print_profile_header,
    print_stats_line,
    print_table_row,
)

try:
    from typing import Final
except ImportError:
    pass

LINE_PIN_NAME: Final = "D9"
RX_PIN_NAME: Final = "A0"
PAYLOAD_LENGTHS: Final = [1, 4, 16, 64]
ITERATIONS_PER_LENGTH: Final = 10
TARGET_FPS: Final = 24.0
LOG_INTERVAL_SECONDS: Final = 5.0


def _build_network_controls() -> HardwareNetworkControls:
    import board

    from hardware.circuitpython.propmaker import setup_ir

    line_pin = getattr(board, LINE_PIN_NAME)
    rx_pin = getattr(board, RX_PIN_NAME)
    transmitters, _receiver = setup_ir(rx_pin, line_pin)
    return HardwareNetworkControls(transmitters)


def run() -> None:
    """Sweep payload length, reporting PulseOut.send blocking duration."""
    network_controls = _build_network_controls()

    print_profile_header(
        component="ir_tx",
        sweep_axes=["payload_length"],
        sweep_values=[PAYLOAD_LENGTHS[0]],
        target_fps=TARGET_FPS,
    )

    # blocking_send_ms is the worst-case PulseOut.send blocking for the longest
    # payload this prop transmits -- track the peak across the sweep.
    worst_blocking_send_ms = 0.0
    for length in PAYLOAD_LENGTHS:
        payload = bytes(i % 256 for i in range(length))
        perf = PerformanceTracker(log_interval=LOG_INTERVAL_SECONDS)

        for _ in range(ITERATIONS_PER_LENGTH):
            perf.start_frame()
            perf.start_update_time()
            send_start = time.monotonic()
            network_controls.send_ir(payload, LINE)
            blocking_send_ms = (time.monotonic() - send_start) * 1000.0
            perf.add_update_time()

            if blocking_send_ms > worst_blocking_send_ms:
                worst_blocking_send_ms = blocking_send_ms

            if perf.complete_frame():
                print_stats_line(
                    perf,
                    payload_length=length,
                    blocking_send_ms=f"{blocking_send_ms:.2f}",
                )

    # cost_ms (average per-frame CPU reservation) depends on send cadence, which
    # this profiler does not sweep -- left _TBD_. blocking_send_ms is measured.
    print_table_row(
        "ir_transmit_component_costs",
        ["_TBD_", f"{worst_blocking_send_ms:.2f}"],
    )


run()
