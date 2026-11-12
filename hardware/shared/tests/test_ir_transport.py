"""Behaviour-driven tests for the Aura IR transport layer.

Covers:
- PulseReader / PulseWriter port contracts
- IR telemetry field ownership (receive behaviour is tested through the
  transceiver in test_ir_transceiver_receive.py)
"""

from array import array

import pytest

from hardware.shared.ir_codecs.base import InfraredDecoder
from hardware.shared.ir_telemetry import IrTelemetrySnapshot
from hardware.shared.ir_transport import (
    PulseReader,
    PulseWriter,
    _InfraredReceiver,
)

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
# Telemetry field ownership
# ---------------------------------------------------------------------------


def test_ir_telemetry_field_ownership_partitions_every_snapshot_field_with_no_overlap():
    """Each IrTelemetrySnapshot field has exactly one declared owner —
    InfraredDecoder, PulseReader, or the receiver. A counter with no
    owner (missing from the union) or two owners (present in more than one
    tuple) fails this test."""
    # Receiver seam: the receiver's own field tuple has no transceiver route,
    # and an overlap would silently overwrite a counter in the telemetry line.
    owned_field_tuples = [
        InfraredDecoder.OWNED_TELEMETRY_FIELDS,
        PulseReader.OWNED_TELEMETRY_FIELDS,
        _InfraredReceiver.OWNED_TELEMETRY_FIELDS,
    ]

    union: set[str] = set()
    for fields in owned_field_tuples:
        assert union.isdisjoint(fields), f"{fields} overlaps an already-claimed field"
        union.update(fields)

    assert union == set(IrTelemetrySnapshot.FIELDS)
