"""Behaviour-driven tests for the Aura IR transport layer.

Covers:
- PulseReader / PulseWriter port contracts
- InfraredReceiver: receives over one or many readers, picking the packet
  with the lowest error margin, and allocates nothing per tick
"""

import tracemalloc
from array import array

import pytest

from hardware.shared.ir_codecs.aura import AuraInfraredDecoder, AuraInfraredEncoder
from hardware.shared.ir_codecs.base import InfraredDecoder
from hardware.shared.ir_codecs.tag import TAG_PREAMBLE, TagInfraredDecoder, TagInfraredEncoder
from hardware.shared.ir_telemetry import IrTelemetrySnapshot
from hardware.shared.ir_transport import (
    InfraredReceiver,
    IrTransmitGate,
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


def _reordered_snapshot_init(
    self,
    packets_surfaced,
    pulses_seen,
    buffer_full_on_poll,
    packets_started,
    preamble_reject,
    mark_reject,
    space_reject,
    packets_completed,
    pulses_dropped_transmitting,
):
    """A stand-in ``IrTelemetrySnapshot.__init__`` with two parameters
    (``pulses_seen``/``packets_surfaced``) swapped relative to ``FIELDS``.

    Used to simulate a future ``FIELDS`` reorder without touching the real
    class. A ``telemetry()`` that still builds positional arguments in the
    old order would silently swap these two counters; one that builds by
    keyword is unaffected."""
    self.pulses_seen = pulses_seen
    self.packets_surfaced = packets_surfaced
    self.buffer_full_on_poll = buffer_full_on_poll
    self.packets_started = packets_started
    self.preamble_reject = preamble_reject
    self.mark_reject = mark_reject
    self.space_reject = space_reject
    self.packets_completed = packets_completed
    self.pulses_dropped_transmitting = pulses_dropped_transmitting


# ---------------------------------------------------------------------------
# InfraredReceiver — fixtures
# ---------------------------------------------------------------------------


def _encode_pulses(payload: bytes):
    return list(AuraInfraredEncoder().encode(payload))


def _make_receiver(num_readers, decoder_factory=AuraInfraredDecoder, gate=None):
    """Build an InfraredReceiver over ``num_readers`` independent FakePulseReaders."""
    readers = [FakePulseReader() for _ in range(num_readers)]
    rx = InfraredReceiver(list(readers), decoder_factory, gate)
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


# ---------------------------------------------------------------------------
# InfraredReceiver — receiving packets
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("num_readers", [1, 3])
def test_receiver_returns_none_when_no_reader_has_pulses(num_readers):
    rx, _ = _make_receiver(num_readers)

    assert rx.receive() is None


def test_receiver_returns_payload_after_complete_packet():
    payload = b"\xde\xad"
    rx, readers = _make_receiver(1)
    readers[0].load(_encode_pulses(payload))

    assert rx.receive() == bytearray(payload)


def test_receiver_assembles_a_packet_fed_across_several_ticks():
    payload = b"\xbe\xef"
    rx, readers = _make_receiver(1)

    result = None
    for pulse in _encode_pulses(payload):
        readers[0].load([pulse])
        result = rx.receive()
        if result is not None:
            break

    assert result == bytearray(payload)


def test_receiver_returns_payload_when_one_of_several_readers_has_a_complete_packet():
    payload = b"\x11\x22"
    rx, readers = _make_receiver(2)
    readers[1].load(_encode_pulses(payload))

    assert rx.receive() == bytearray(payload)


def test_receiver_surfaces_at_most_one_packet_per_reader_per_tick():
    """Two back-to-back packets buffered on one reader surface one tick apart."""
    rx, readers = _make_receiver(1)
    readers[0].load(_encode_pulses(b"\x01") + _encode_pulses(b"\x02"))

    assert rx.receive() == bytearray(b"\x01")
    assert rx.receive() == bytearray(b"\x02")


# ---------------------------------------------------------------------------
# InfraredReceiver — lowest-error-margin selection
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("clean_index", [0, 1])
def test_receiver_picks_the_packet_with_the_lowest_error_margin(clean_index):
    payload = b"\xab"
    pulses_clean = _encode_pulses(payload)
    pulses_noisy = _encode_pulses(payload)
    pulses_noisy[3] += 80  # 80 µs deviation — still within threshold

    rx, readers = _make_receiver(2)
    readers[clean_index].load(pulses_clean)
    readers[1 - clean_index].load(pulses_noisy)

    assert rx.receive() == bytearray(payload)
    assert rx.last_error_margin == 0
    assert rx.last_best_receiver is readers[clean_index]


def test_receiver_picks_the_first_reader_on_an_error_margin_tie():
    payload = b"\x5a"
    rx, readers = _make_receiver(3)
    readers[1].load(_encode_pulses(payload))
    readers[2].load(_encode_pulses(payload))

    rx.receive()

    assert rx.last_best_receiver is readers[1]


def test_receiver_reports_the_winning_readers_signal():
    payload = b"\x99"
    rx, readers = _make_receiver(3)
    readers[2].load(_encode_pulses(payload))

    rx.receive()

    assert rx.last_signal_strength == 1.0
    assert rx.last_error_margin == 0
    assert rx.last_best_receiver is readers[2]


def test_receiver_reports_no_signal_before_the_first_packet():
    rx, _ = _make_receiver(2)

    assert rx.last_signal_strength is None
    assert rx.last_error_margin is None
    assert rx.last_best_receiver is None


def test_single_reader_receiver_reports_signal_but_no_best_receiver():
    """With one reader there is no pick to report, but the signal still is."""
    rx, readers = _make_receiver(1)
    readers[0].load(_encode_pulses(b"\x42"))

    rx.receive()

    assert rx.last_signal_strength == 1.0
    assert rx.last_error_margin == 0
    assert rx.last_best_receiver is None


# ---------------------------------------------------------------------------
# InfraredReceiver — telemetry counters
# ---------------------------------------------------------------------------


def test_receiver_pulses_seen_counts_every_pulse_across_readers_and_ticks():
    rx, readers = _make_receiver(2)
    readers[0].load([100, 200])
    readers[1].load([300])
    rx.receive()
    readers[0].load([400])
    rx.receive()

    assert rx.telemetry().pulses_seen == 4


def test_receiver_packets_surfaced_counts_only_winning_packets():
    rx, readers = _make_receiver(2)
    readers[0].load(_encode_pulses(b"\x01"))
    rx.receive()
    readers[1].load([100, 200])  # noise, no packet
    rx.receive()

    assert rx.telemetry().packets_surfaced == 1


def test_receiver_telemetry_sums_decoder_counters_across_readers():
    bad_preamble = list(TAG_PREAMBLE)
    bad_preamble[1] = 4000  # invalid but below the inter-frame gap threshold
    rx, readers = _make_receiver(2, TagInfraredDecoder)
    readers[0].load(bad_preamble)
    readers[1].load(bad_preamble)

    rx.receive()

    assert rx.telemetry().preamble_reject == 2


def test_receiver_telemetry_sums_buffer_full_on_poll_across_readers():
    rx, readers = _make_receiver(3)
    readers[0].buffer_full_on_poll = 2
    readers[2].buffer_full_on_poll = 5

    assert rx.telemetry().buffer_full_on_poll == 7


def test_receiver_packets_completed_can_exceed_surfaced_on_simultaneous_wins():
    """Dedup, not loss: two decoders independently completing the same shot in
    one tick both count toward (summed) packets_completed, but only the
    lowest-error-margin winner surfaces from receive()."""
    pulses = list(TagInfraredEncoder().encode(bytearray([0x10])))
    rx, readers = _make_receiver(3, TagInfraredDecoder)
    readers[0].load(pulses)
    readers[2].load(pulses)

    rx.receive()

    snapshot = rx.telemetry()
    assert snapshot.packets_completed == 2
    assert snapshot.packets_surfaced == 1


def test_receiver_telemetry_survives_a_fields_reorder(monkeypatch):
    """A ``FIELDS`` reorder (simulated here by an ``IrTelemetrySnapshot``
    constructor with two parameters swapped) must not swap counters — proves
    ``telemetry()`` builds the snapshot by keyword, not position."""
    monkeypatch.setattr(IrTelemetrySnapshot, "__init__", _reordered_snapshot_init)
    pulses = _encode_pulses(b"\xde\xad")
    rx, readers = _make_receiver(1)
    readers[0].load(pulses)

    rx.receive()
    snapshot = rx.telemetry()

    assert snapshot.pulses_seen == len(pulses)
    assert snapshot.packets_surfaced == 1


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


# ---------------------------------------------------------------------------
# InfraredReceiver — telemetry_line() change-gating
# ---------------------------------------------------------------------------


def test_receiver_telemetry_line_reports_on_first_call():
    """The very first call has no prior baseline, so it always reports."""
    rx, _ = _make_receiver(1)

    assert rx.telemetry_line() is not None


def test_receiver_telemetry_line_is_none_when_nothing_changed():
    rx, _ = _make_receiver(1)
    rx.telemetry_line()

    assert rx.telemetry_line() is None


def test_receiver_telemetry_line_reports_the_pipeline_format_after_a_packet():
    pulses = _encode_pulses(b"\x42")
    rx, readers = _make_receiver(1)
    readers[0].load(pulses)

    rx.receive()
    line = rx.telemetry_line()

    assert line == (
        "ir: pulses_seen=" + str(len(pulses)) + " buffer_full_on_poll=0 "
        "packets_started=0 preamble_reject=0 mark_reject=0 space_reject=0 "
        "packets_completed=0 packets_surfaced=1 pulses_dropped_transmitting=0"
    )


def test_receiver_telemetry_line_reports_again_after_reset_telemetry():
    """reset_telemetry() clears the change-gate baseline along with the counters."""
    rx, _ = _make_receiver(1)
    rx.telemetry_line()

    rx.reset_telemetry()

    assert rx.telemetry_line() is not None


# ---------------------------------------------------------------------------
# InfraredReceiver — gate-driven self-echo suppression
# ---------------------------------------------------------------------------


def test_receiver_drops_echo_on_every_reader_while_transmitting():
    gate = IrTransmitGate()
    gate.begin_transmit()
    rx, readers = _make_receiver(3, gate=gate)
    payload = b"\x33"
    readers[0].load(_encode_pulses(payload))
    readers[2].load(_encode_pulses(payload))

    assert rx.receive() is None


def test_receiver_counts_dropped_pulses_from_every_reader_apart_from_pulses_seen():
    gate = IrTransmitGate()
    gate.begin_transmit()
    rx, readers = _make_receiver(2, gate=gate)
    readers[0].load([100, 200])
    readers[1].load([300, 400, 500])

    rx.receive()

    snapshot = rx.telemetry()
    assert snapshot.pulses_dropped_transmitting == 5
    assert snapshot.pulses_seen == 0


def test_receiver_partial_decode_in_progress_when_transmit_begins_is_reset_on_every_reader():
    pulses = _encode_pulses(b"\x44")
    mid = len(pulses) // 2
    gate = IrTransmitGate()
    rx, readers = _make_receiver(2, gate=gate)
    readers[0].load(pulses[:mid])
    readers[1].load(pulses[:mid])
    rx.receive()  # both readers mid-decode, gate idle

    gate.begin_transmit()
    rx.receive()  # the drop resets both decoders, even with nothing buffered
    gate.end_transmit()
    rx.receive()  # consume the flush

    readers[0].load(pulses[mid:])
    readers[1].load(pulses[mid:])
    assert rx.receive() is None


def test_receiver_partial_decode_in_progress_when_transmit_ends_is_reset():
    """A decode mid-flight at the falling-edge flush does not survive it either."""
    pulses = _encode_pulses(b"\xde\xad")
    mid = len(pulses) // 2
    gate = IrTransmitGate()
    rx, readers = _make_receiver(1, gate=gate)

    gate.begin_transmit()
    readers[0].load(pulses[:mid])  # echo pulses captured mid-emission
    rx.receive()

    gate.end_transmit()
    rx.receive()  # falling-edge flush resets the decoder

    readers[0].load(pulses[mid:])
    assert rx.receive() is None


def test_receiver_falling_edge_discards_the_buffered_echo_tail():
    gate = IrTransmitGate()
    gate.begin_transmit()
    gate.end_transmit()
    rx, readers = _make_receiver(2, gate=gate)
    readers[0].load([111, 222])  # buffered echo tail

    rx.receive()

    assert rx.telemetry().pulses_dropped_transmitting == 2


def test_receiver_decodes_normally_after_the_one_shot_falling_edge_flush():
    gate = IrTransmitGate()
    gate.begin_transmit()
    gate.end_transmit()
    rx, readers = _make_receiver(2, gate=gate)
    rx.receive()  # consumes the one-shot flush

    payload = b"\x21"
    readers[1].load(_encode_pulses(payload))
    assert rx.receive() == bytearray(payload)


# ---------------------------------------------------------------------------
# InfraredReceiver — no per-tick allocation in polled path
# ---------------------------------------------------------------------------


def _allocations_in_ir_transport_over_100_receives(rx):
    """Return the ir_transport.py allocation growth across 100 ``receive()`` calls.

    Uses ``tracemalloc`` snapshot comparison rather than ``gc.get_count()`` so
    that transient (immediately-freed) per-tick allocations are also detected.
    Only allocations attributed to ``ir_transport.py`` are checked — this
    filters out tracemalloc's own internal overhead.
    """
    # Warm up: let any one-time setup allocations settle
    for _ in range(5):
        rx.receive()

    tracemalloc.start()
    before = tracemalloc.take_snapshot()

    for _ in range(100):
        rx.receive()

    after = tracemalloc.take_snapshot()
    tracemalloc.stop()

    return [
        stat
        for stat in after.compare_to(before, "lineno")
        if stat.traceback[0].filename.endswith("/ir_transport.py") and stat.size_diff > 0
    ]


@pytest.mark.parametrize("num_readers", [1, 3])
def test_receiver_receive_allocates_nothing_per_tick_when_no_packet(num_readers):
    rx, _ = _make_receiver(num_readers)

    diff = _allocations_in_ir_transport_over_100_receives(rx)

    assert not diff, f"Unexpected allocations in ir_transport.py during idle receive: {diff}"


def test_receiver_drop_path_allocates_nothing_per_tick():
    """The gated drain-but-discard path must not allocate per tick either.

    Uses readers with nothing buffered (the common steady-state tick while
    emitting) so the only thing exercised repeatedly is the drain loop and
    the gate check — not a growing counter, whose own integer-widening as it
    crosses CPython's small-int cache is an unrelated, unavoidable artifact
    of any incrementing counter and would otherwise produce a false positive.
    """
    gate = IrTransmitGate()
    gate.begin_transmit()
    rx, _ = _make_receiver(3, gate=gate)

    diff = _allocations_in_ir_transport_over_100_receives(rx)

    assert not diff, f"Unexpected allocations in ir_transport.py during drop receive: {diff}"


# ---------------------------------------------------------------------------
# InfraredReceiver — set_decoder
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("num_readers", [1, 2])
def test_receiver_set_decoder_decodes_through_the_new_decoder_type(num_readers):
    """A packet encoded for the Tag protocol only decodes once the receiver's
    decoders are swapped from Aura to Tag."""
    payload = bytearray([0x10])
    rx, readers = _make_receiver(num_readers)

    rx.set_decoder(TagInfraredDecoder)
    readers[-1].load(list(TagInfraredEncoder().encode(payload)))

    assert rx.receive() == payload


def test_receiver_set_decoder_gives_each_reader_its_own_fresh_decoder(recording_tag_decoder):
    decoder_factory, built = recording_tag_decoder
    rx, _ = _make_receiver(2)

    rx.set_decoder(decoder_factory)

    assert len(built) == 2
    assert built[0] is not built[1]


def test_receiver_set_decoder_keeps_a_partial_decode_on_one_reader_from_corrupting_another():
    payload = bytearray([0x30])
    pulses = list(TagInfraredEncoder().encode(payload))
    mid = len(pulses) // 2
    rx, readers = _make_receiver(2)
    rx.set_decoder(TagInfraredDecoder)

    readers[0].load(pulses[:mid])  # reader 0 left mid-decode, never completes
    rx.receive()

    readers[1].load(pulses)  # reader 1's independent, complete packet
    assert rx.receive() == payload


def test_receiver_set_decoder_reports_telemetry_from_the_new_decoders():
    bad_preamble = list(TAG_PREAMBLE)
    bad_preamble[1] = 4000  # invalid but below the inter-frame gap threshold
    rx, readers = _make_receiver(1)
    rx.set_decoder(TagInfraredDecoder)
    readers[0].load(bad_preamble)

    rx.receive()

    assert rx.telemetry().preamble_reject == 1
