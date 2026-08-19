"""CircuitPython IR-rx packet source -- the external transmitter companion to
`ir_rx_profiler.py` (see `docs/hardware/calibration-guide.md`).

`ir_rx_profiler.py` locates the receiver's `max_frame_ms` by counting gaps in a
sequence number encoded in byte 0 of each received packet. On a bare board no
packets arrive and it can only emit `_TBD_`. Run **this** script on a *second*
board (or a loopback emitter pointed at the profiler's receivers) to supply that
known incoming packet stream: it transmits fixed-size packets whose first byte is
an incrementing sequence number (wrapping at 256, matching the profiler's
`(sequence - last_sequence) % 256` gap logic), driven via the same
`HardwareNetworkControls.send_ir` / LINE path as `ir_tx_profiler.py`.

The sustained send rate is **measured and printed** as `send_rate_hz`: with
`DELAY_MS = 0` the rate is bounded by `PulseOut.send`'s blocking duration for the
chosen `PACKET_SIZE` (~17 Hz for a 4-byte packet on the RP2040, given the ~60 ms
blocking measured by `ir_tx_profiler.py`), not the instruction loop. Read the
reported `send_rate_hz` off this board's serial output and set the profiler's
`INCOMING_RATE_HZ` to match, so its recorded deadline is keyed to the real rate.
Raise `DELAY_MS` to throttle to a lower, rounder rate.

Hardware
--------
- IR emitter (LINE) wired to the pin declared by `ir.line` in the real
  `aura-device.json`, driven via `pulseio.PulseOut` at 38kHz through
  `device_builder.build_hardware`, aimed at the profiler board's IR receivers.
- IR receiver wired to the pin declared by `ir.rx` -- unused by this script, but
  `build_hardware` wires a receiver alongside the LINE emitter whenever the `ir`
  section is declared and enabled.
- `pixels`/`audio`/`accelerometer`/`haptics`/`radio` -- whatever the real config
  declares for them -- are disabled via `config.isolate(keep="ir")` (#715, #717),
  since this script drives IR only.

Installation
------------
1. Install CircuitPython on the transmitter board:
   https://learn.adafruit.com/welcome-to-circuitpython/installing-circuitpython

2. Run the deploy script to copy all source files and set code.py:
     python scripts/deploy.py examples/hardware/profiling/ir_rx_packet_source.py
   The board reboots and starts transmitting automatically.

Configuration
-------------
- The real, deployed `aura-device.json` on the CIRCUITPY drive is loaded via
  `load_device_config()` and handed to `build_hardware` wholesale (after isolating
  the one section this script drives) -- the `ir.line` / `ir.rx` pins are
  whatever the config declares, not harvested and re-assembled into a private
  mapping. A config declaring no `ir` section fails loudly at bring-up.
- PACKET_SIZE: bytes per transmitted packet (byte 0 is the sequence number);
  defaults to 4 to match the realistic AURA payload
- DELAY_MS: delay inserted after each send to throttle the rate; defaults to 0
  (send back-to-back, bounded only by PulseOut.send's blocking duration)
- LOG_INTERVAL_SECONDS: how often the status line is printed
"""

from __future__ import annotations

import time

from engine.network import LINE
from hardware.shared.device_config import DeviceConfig, load_device_config
from hardware.shared.ir_transceiver import InfraredTransceiver
from hardware.shared.network_controls import HardwareNetworkControls
from hardware.shared.profiler_report import board_id, runtime_id

try:
    from typing import Final
except ImportError:
    pass

PACKET_SIZE: Final = 4
DELAY_MS: Final = 0.0
LOG_INTERVAL_SECONDS: Final = 5.0


def _isolate_ir_config(config: DeviceConfig) -> DeviceConfig:
    """Return a derived config isolating `ir` on *config*.

    This script drives the LINE emitter only, so everything but `ir` is disabled via
    `config.isolate(keep="ir")` -- the non-destructive isolation knob alongside
    dropping a section from aura-device.json outright. `ir` itself is left
    exactly as declared: its `rx`/`line`/`cone`/`area_of_effect` pins are the real
    prop's wiring, not a hand-harvested-and-rebuilt mapping.

    Raises:
        ValueError: If *config* declares no `ir` section at all.
    """
    if config.ir is None:
        raise ValueError("ir not declared in aura-device.json -- required to transmit on LINE")
    return config.isolate(keep="ir")


def _build_network_controls() -> tuple[HardwareNetworkControls, InfraredTransceiver]:
    """Build the send-only seam plus the transceiver it delegates to.

    The transceiver is returned alongside `hw.network_controls` because
    `run()`'s busy-gating loop (see its own docstring) needs LINE's raw
    busy state -- a runtime-lifecycle detail `HardwareNetworkControls`
    deliberately never surfaces (it is send-only, matching
    `NetworkControls`). `InfraredTransceiver.busy` is the public seam for
    LINE's raw busy state -- it never surfaces through
    `HardwareNetworkControls`, which is send-only.
    """
    from hardware.circuitpython.device_builder import build_hardware

    device_config = load_device_config()
    device_config = _isolate_ir_config(device_config)
    hw = build_hardware(device_config)
    return hw.network_controls, hw.ir


def _send_packet(network_controls: HardwareNetworkControls, payload: bytes) -> None:
    """Transmit one packet via the LINE emitter.

    Raises:
        RuntimeError: If the hardware bundle has no LINE transmitter wired --
            `send_ir` already raises `ValueError` for this, but names only the
            emitter constant; re-raised here with a wiring hint pointing at
            `ir.line` so a bring-up mistake is diagnosable from the message
            alone.
    """
    try:
        network_controls.send_ir(payload, LINE)
    except ValueError as exc:
        raise RuntimeError(
            "no LINE transmitter in the built hardware bundle -- check ir.line wiring"
        ) from exc


def run() -> None:
    """Transmit sequence-numbered packets, reporting the sustained send rate."""
    network_controls, ir = _build_network_controls()

    print(
        f"__IR_RX_PACKET_SOURCE packet_size={PACKET_SIZE}, "
        + f"delay_ms={DELAY_MS:.1f}, "
        + f"board={board_id()}, "
        + f"runtime={runtime_id()}"
    )

    # Pre-allocate the payload once and mutate byte 0 each send -- the only byte
    # the profiler reads. Padding bytes carry a fixed non-zero marker so the
    # encoded frame is not a degenerate run of zeros.
    payload = bytearray(PACKET_SIZE)
    for i in range(1, PACKET_SIZE):
        payload[i] = 0xA0 | (i & 0x0F)

    sequence = 0
    packets_sent = 0
    start_time = time.monotonic()
    next_log_time = start_time + LOG_INTERVAL_SECONDS

    while True:
        # Poll exactly once per iteration -- the LINE busy state it reports
        # gates whether this iteration builds/sends a payload at all, so a
        # transmit still in flight is never overwritten with a fresh one.
        line_busy = ir.busy(LINE)

        if not line_busy:
            payload[0] = sequence & 0xFF
            # An idle writer always starts the transmit immediately (it never
            # buffers), so a send issued here is a real transmit start -- the
            # advance keys off this idle pre-check, not send_ir's return.
            _send_packet(network_controls, payload)
            sequence += 1
            packets_sent += 1

        if DELAY_MS > 0:
            time.sleep(DELAY_MS / 1000.0)

        current_time = time.monotonic()
        if current_time >= next_log_time:
            elapsed = current_time - start_time
            send_rate_hz = packets_sent / elapsed if elapsed > 0 else 0.0
            print(
                f"__IR_TX packets_sent={packets_sent}, "
                + f"send_rate_hz={send_rate_hz:.2f}, "
                + f"packet_size={PACKET_SIZE}, "
                + f"delay_ms={DELAY_MS:.1f}"
            )
            next_log_time = current_time + LOG_INTERVAL_SECONDS


run()
