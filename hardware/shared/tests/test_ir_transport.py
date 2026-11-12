"""Behaviour-driven tests for the Aura IR transport layer.

Covers:
- PulseReader / PulseWriter port contracts
- InfraredReceiver: telemetry field ownership and reset (receive behaviour
  is tested through the transceiver in test_ir_transceiver_receive.py)
"""

from array import array

import pytest

from hardware.shared.ir_codecs.aura import AuraInfraredDecoder
from hardware.shared.ir_codecs.base import InfraredDecoder
from hardware.shared.ir_codecs.tag import TagInfraredDecoder
from hardware.shared.ir_telemetry import IrTelemetrySnapshot
from hardware.shared.ir_transport import (
    InfraredReceiver,
    PulseReader,
    PulseWriter,
)

# ---------------------------------------------------------------------------
# Local copies of wire-frame constants used by tests to nudge pulses.
# ---------------------------------------------------------------------------

_IR_UNIT = 500
_IR_HEADER_MARK = 4000
_IR_HEADER_SPACE = 3000
_IR_LEAD_OUT = 5000
_IR_SPACE_ZERO = _IR_UNIT
_IR_SPACE_ONE = _IR_UNIT * 3
_IR_ERROR_THRESHOLD = _IR_UNIT // 2  # 250 µs


# ---------------------------------------------------------------------------
# Fake ports
# ---------------------------------------------------------------------------


class FakePulseReader(PulseReader):
    """Replaying fake — drains a queue of pre-loaded pulses one at a time."""

    def __init__(self, pulses=None):
        self._queue = list(pulses) if pulses else []

    def load(self, pulses) -> None:
        """Replace the pending pulse queue."""
        self._queue = list(pulses)

    def read_pulse(self) -> "int | None":
        if self._queue:
            return self._queue.pop(0)
        return None


# ---------------------------------------------------------------------------
# Port contracts
# ---------------------------------------------------------------------------


def test_pulse_writer_base_raises_not_implemented():
    writer = PulseWriter()
    with pytest.raises(NotImplementedError):
        writer.write_pulses(array("H", [500]))


def test_pulse_reader_base_raises_not_implemented():
    reader = PulseReader()
    with pytest.raises(NotImplementedError):
        reader.read_pulse()


def test_pulse_writer_base_is_busy_raises_not_implemented():
    writer = PulseWriter()
    with pytest.raises(NotImplementedError):
        writer.is_busy()


# ---------------------------------------------------------------------------
# InfraredReceiver — telemetry ownership and reset
#
# Receive behaviour is tested through the transceiver in
# test_ir_transceiver_receive.py. What stays here has no transceiver route.
# ---------------------------------------------------------------------------


def _make_receiver(num_readers, decoder_factory=AuraInfraredDecoder):
    """Build an InfraredReceiver over ``num_readers`` independent FakePulseReaders."""
    readers = [FakePulseReader() for _ in range(num_readers)]
    rx = InfraredReceiver(list(readers), decoder_factory)
    return rx, readers


@pytest.fixture
def recording_tag_decoder():
    """A Tag decoder class that records every instance built, paired with that
    record, so a test can reach the decoders a receiver built for itself."""
    built: list[TagInfraredDecoder] = []

    class RecordingTagDecoder(TagInfraredDecoder):
        def __init__(self):
            super().__init__()
            built.append(self)

    return RecordingTagDecoder, built


def test_ir_telemetry_field_ownership_partitions_every_snapshot_field_with_no_overlap():
    """Each IrTelemetrySnapshot field has exactly one declared owner —
    InfraredDecoder, PulseReader, or InfraredReceiver. A counter with no
    owner (missing from the union) or two owners (present in more than one
    tuple) fails this test."""
    owned_field_tuples = [
        InfraredDecoder.OWNED_TELEMETRY_FIELDS,
        PulseReader.OWNED_TELEMETRY_FIELDS,
        InfraredReceiver.OWNED_TELEMETRY_FIELDS,
    ]

    union: set[str] = set()
    for fields in owned_field_tuples:
        assert union.isdisjoint(fields), f"{fields} overlaps an already-claimed field"
        union.update(fields)

    assert union == set(IrTelemetrySnapshot.FIELDS)


@pytest.mark.parametrize("num_readers", [1, 2])
def test_receiver_reset_telemetry_zeroes_every_counter_telemetry_reports(
    num_readers, recording_tag_decoder
):
    """Read/reset symmetry: whatever telemetry() reports, reset_telemetry()
    zeroes — checked generically across every declared counter on every
    reader and decoder, so a newly added counter is covered automatically."""
    # Receiver seam: reset_telemetry has no route through the transceiver.
    decoder_factory, built = recording_tag_decoder
    rx, readers = _make_receiver(num_readers, decoder_factory)
    for name in InfraredDecoder.OWNED_TELEMETRY_FIELDS:
        for decoder in built:
            setattr(decoder, name, 7)
    for name in PulseReader.OWNED_TELEMETRY_FIELDS:
        for reader in readers:
            setattr(reader, name, 7)
    for name in InfraredReceiver.OWNED_TELEMETRY_FIELDS:
        setattr(rx, name, 7)

    before = rx.telemetry()
    assert all(getattr(before, field) >= 7 for field in IrTelemetrySnapshot.FIELDS)

    rx.reset_telemetry()

    after = rx.telemetry()
    assert all(getattr(after, field) == 0 for field in IrTelemetrySnapshot.FIELDS)


def test_receiver_telemetry_line_reports_again_after_reset_telemetry():
    """reset_telemetry() clears the change-gate baseline along with the counters."""
    # Receiver seam: reset_telemetry has no route through the transceiver.
    rx, _ = _make_receiver(1)
    rx.telemetry_line()

    rx.reset_telemetry()

    assert rx.telemetry_line() is not None
