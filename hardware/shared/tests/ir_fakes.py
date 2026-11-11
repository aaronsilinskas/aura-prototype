"""Hardware-free fakes for the infrared transmit path."""

from __future__ import annotations

from array import array

from hardware.shared.ir_codecs.base import InfraredEncoder
from hardware.shared.ir_transport import InfraredTransmitter, PulseWriter


class RecordingPulseWriter(PulseWriter):
    """Captures written pulse sequences without touching hardware.

    ``is_busy()`` always reports ``False`` — matches the blocking
    ``PulseOutWriter``'s externally-observable behaviour.
    """

    def __init__(self) -> None:
        self.calls: list[list[int]] = []

    def write_pulses(self, durations: array[int]) -> None:
        self.calls.append(list(durations))

    def is_busy(self) -> bool:
        return False


class StubEncoder(InfraredEncoder):
    """Minimal encoder that converts each byte to a single pulse duration."""

    def encode(self, data: bytes) -> array[int]:
        return array("H", list(data))


def make_transmitter() -> tuple[InfraredTransmitter, RecordingPulseWriter]:
    """A transmitter over a ``StubEncoder``, and the writer recording what it sends."""
    writer = RecordingPulseWriter()
    tx = InfraredTransmitter(writer, StubEncoder())
    return tx, writer
