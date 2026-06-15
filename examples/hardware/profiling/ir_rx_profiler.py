"""CircuitPython IR-rx profiler -- empirically locates `max_frame_ms` for the
capacity estimator's receiver deadline model (see `docs/hardware/capacity-model.md`
and #397).

Drives the real `InfraredMultiReceiver.receive()` polling loop over the fixed 4
`PulseInReader`s using the **tunable-injected-load technique**: each frame, after
polling the receivers, an artificial per-frame busy-loop (`INJECTED_LOAD_MS`) is
executed to simulate co-located CPU load. `INJECTED_LOAD_MS` is swept upward across
`INJECTED_LOAD_SWEEP_MS` until packets start dropping -- the injected load at which
the packet-loss rate first becomes non-zero is the empirical `max_frame_ms` for the
profiled `PulseIn.maxlen` (buffer depth) and incoming rate.

Packet loss is measured by counting packets received against a sequence number
encoded by the transmitter (a known incoming rate via loopback from an IR
transmitter or a second board running `ir_tx_profiler`-style code). A gap in the
sequence counts as a dropped packet.

This profiler reports packet-loss rate vs. injected frame time, alongside the
uniform `PerformanceTracker` stats line (including `frame_time_peak`, the worst-case
single frame -- the `worst_case_frame_ms` term the estimator compares against
`max_frame_ms`).

Hardware
--------
- 4 IR receivers wired to `RX_PINS`, each as a `pulseio.PulseIn(pin, maxlen=BUFFER_DEPTH,
  idle_state=True)`.
- A known incoming packet rate via loopback from an IR transmitter or a second board,
  sending sequence-numbered packets at `INCOMING_RATE_HZ`.

Installation
------------
1. Install CircuitPython on your board:
   https://learn.adafruit.com/welcome-to-circuitpython/installing-circuitpython

2. Run the deploy script to copy all source files and set code.py:
     python scripts/deploy.py examples/hardware/profiling/ir_rx_profiler.py
   The board reboots and starts running automatically.

Configuration
-------------
- RX_PINS: board pins for the 4 fixed `PulseInReader`s
- BUFFER_DEPTH: `PulseIn.maxlen` -- the RAM-for-deadline knob (#397)
- INCOMING_RATE_HZ: known incoming packet rate from the loopback transmitter
- INJECTED_LOAD_SWEEP_MS: per-frame injected busy-loop durations to sweep, in order
- DISPLAY_SECONDS: how long to spend at each injected-load level before advancing
- LOG_INTERVAL_SECONDS: how often the stats line is printed
- TARGET_FPS: informational only -- included in the header for comparison against
  other profilers
"""

from __future__ import annotations

import time

from effects.performance import PerformanceTracker
from hardware.shared.ir_protocol import AuraInfraredDecoder
from hardware.shared.ir_transport import InfraredMultiReceiver
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

# Fixed at 4 receivers -- not a deployment axis (#397).
RX_PIN_NAMES: Final = ("A0", "A1", "A2", "A3")
BUFFER_DEPTH: Final = 64
INCOMING_RATE_HZ: Final = 50.0
INJECTED_LOAD_SWEEP_MS: Final = [0.0, 5.0, 10.0, 20.0, 40.0, 80.0]
DISPLAY_SECONDS: Final = 10.0
LOG_INTERVAL_SECONDS: Final = 5.0
TARGET_FPS: Final = 24.0


def _build_readers() -> list:
    import board
    import pulseio

    from hardware.circuitpython.infrared_io import PulseInReader

    readers = []
    for pin_name in RX_PIN_NAMES:
        pin = getattr(board, pin_name)
        pulsein = pulseio.PulseIn(pin, maxlen=BUFFER_DEPTH, idle_state=True)
        readers.append(PulseInReader(pulsein))
    return readers


def _busy_wait_ms(duration_ms: float) -> None:
    """Burn CPU for `duration_ms` -- the tunable injected per-frame load."""
    if duration_ms <= 0:
        return
    end = time.monotonic() + duration_ms / 1000.0
    while time.monotonic() < end:
        pass


def run() -> None:
    """Sweep injected per-frame load, reporting packet-loss rate vs. frame time."""
    readers = _build_readers()
    receiver = InfraredMultiReceiver(readers, AuraInfraredDecoder)

    print_profile_header(
        component="ir_rx",
        sweep_axes=["injected_load_ms", "buffer_depth", "incoming_rate_hz"],
        sweep_values=[INJECTED_LOAD_SWEEP_MS[0], BUFFER_DEPTH, INCOMING_RATE_HZ],
        target_fps=TARGET_FPS,
    )

    # max_frame_ms is the injected frame time at which packet loss first becomes
    # non-zero. Track each point's peak frame time, its loss, and whether any
    # packet arrived (a bare board with no external IR source receives none).
    total_received = 0
    max_frame_ms = "_TBD_"
    for injected_load_ms in INJECTED_LOAD_SWEEP_MS:
        perf = PerformanceTracker(log_interval=LOG_INTERVAL_SECONDS)
        last_sequence = None
        packets_received = 0
        packets_dropped = 0

        next_change_time = time.monotonic() + DISPLAY_SECONDS
        while True:
            current_time = time.monotonic()

            perf.start_frame()
            perf.start_update_time()
            packet = receiver.receive()
            if packet is not None and len(packet) >= 1:
                sequence = packet[0]
                if last_sequence is not None:
                    gap = (sequence - last_sequence) % 256
                    if gap > 1:
                        packets_dropped += gap - 1
                last_sequence = sequence
                packets_received += 1
            _busy_wait_ms(injected_load_ms)
            perf.add_update_time()

            due = stats_due(perf, current_time)
            perf.complete_frame(current_time)
            if due:
                total_packets = packets_received + packets_dropped
                loss_rate = packets_dropped / total_packets if total_packets > 0 else 0.0
                print_stats_line(
                    perf,
                    current_time,
                    injected_load_ms=injected_load_ms,
                    buffer_depth=BUFFER_DEPTH,
                    incoming_rate_hz=INCOMING_RATE_HZ,
                    packets_received=packets_received,
                    packets_dropped=packets_dropped,
                    packet_loss_rate=f"{loss_rate:.4f}",
                    frame_time_peak_ms=f"{perf.frame_time_peak * 1000.0:.2f}",
                )

            if current_time > next_change_time:
                break

        total_received += packets_received
        total_packets = packets_received + packets_dropped
        loss_rate = packets_dropped / total_packets if total_packets > 0 else 0.0
        # First point that drops packets locates the deadline; keep the earliest.
        if loss_rate > 0.0 and max_frame_ms == "_TBD_":
            max_frame_ms = f"{perf.frame_time_peak * 1000.0:.2f}"

    # No packets at all means no external IR source was driving the loopback, so
    # the deadline cannot be located on this run -- emit _TBD_ for max_frame_ms.
    if total_received == 0:
        max_frame_ms = "_TBD_"

    print_table_row(
        "ir_receive_component_costs",
        [BUFFER_DEPTH, f"{INCOMING_RATE_HZ:.1f}", max_frame_ms],
    )


run()
