"""Receive-side IR behaviour, driven through InfraredTransceiver with fake pulse readers.

Every transceiver here is built from fake pulse readers and writers; tests
feed pulses to fake readers, call ``update`` (and ``send`` / ``apply_codec``
where emission or a codec swap matters) and assert on what a caller reads
back: ``received``, the signal values, the best receiver, the telemetry line
and ``receives``.
"""

import tracemalloc

import pytest

from engine.network import LINE
from hardware.shared.ir_codecs.aura import AuraInfraredEncoder
from hardware.shared.ir_codecs.tag import (
    TAG_GAP_THRESHOLD,
    TAG_PREAMBLE,
    TagInfraredDecoder,
    TagInfraredEncoder,
)
from hardware.shared.ir_telemetry import IrTelemetrySnapshot
from hardware.shared.ir_transceiver import InfraredTransceiver
from hardware.shared.tests.ir_fakes import (
    EmitterPulseWriter,
    EmitterWriterFactory,
    ReplayingPulseReader,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _receiving(reader_count: int) -> tuple[InfraredTransceiver, list[ReplayingPulseReader]]:
    """A transceiver with *reader_count* fake readers and no emitter."""
    readers = [ReplayingPulseReader() for _ in range(reader_count)]
    return InfraredTransceiver(list(readers), {}, EmitterWriterFactory()), readers


def _emitting(
    reader_count: int, holds: bool
) -> tuple[InfraredTransceiver, list[ReplayingPulseReader], EmitterPulseWriter]:
    """A transceiver with fake readers and a LINE emitter, plus that emitter's writer.

    With *holds*, the writer stays busy after a write until its ``finish()``,
    keeping the device emitting across ticks like a DMA-backed writer
    mid-frame; otherwise it finishes inline, like the blocking writer.
    """
    readers = [ReplayingPulseReader() for _ in range(reader_count)]
    factory = EmitterWriterFactory(blocking=not holds)
    transceiver = InfraredTransceiver(list(readers), {LINE: "GP1"}, factory)
    return transceiver, readers, factory.writers[LINE]


def _aura_pulses(payload: bytes) -> list[int]:
    return list(AuraInfraredEncoder().encode(payload))


def _tag_pulses(payload: bytes) -> list[int]:
    return list(TagInfraredEncoder().encode(bytearray(payload)))


def _counters(transceiver: InfraredTransceiver) -> dict[str, int]:
    """Parse the transceiver's telemetry line into ``{counter: value}``.

    Only valid on a call that reports — the first call, or one after a change.
    """
    line = transceiver.telemetry_line()
    assert line is not None
    return {name: int(value) for name, value in (f.split("=") for f in line.split()[1:])}


# ---------------------------------------------------------------------------
# Receiving frames
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("reader_count", [1, 3])
def test_received_is_none_when_no_reader_has_pulses(reader_count):
    transceiver, _ = _receiving(reader_count)

    transceiver.update(0.0)

    assert transceiver.received is None


def test_a_valid_frame_is_received_after_one_update():
    transceiver, readers = _receiving(1)
    readers[0].load(_aura_pulses(b"\xde\xad"))

    transceiver.update(0.0)

    assert transceiver.received == bytearray(b"\xde\xad")


def test_a_received_frame_reports_its_signal_strength_and_error_margin():
    transceiver, readers = _receiving(1)
    readers[0].load(_aura_pulses(b"\x42"))

    transceiver.update(0.0)

    assert transceiver.last_signal_strength == 1.0
    assert transceiver.last_error_margin == 0


def test_received_is_cleared_by_the_next_update_with_no_frame():
    transceiver, readers = _receiving(1)
    readers[0].load(_aura_pulses(b"\x42"))
    transceiver.update(0.0)

    transceiver.update(0.0)

    assert transceiver.received is None


def test_a_frame_fed_across_several_updates_is_received_once_complete():
    transceiver, readers = _receiving(1)

    for pulse in _aura_pulses(b"\xbe\xef"):
        readers[0].load([pulse])
        transceiver.update(0.0)

    assert transceiver.received == bytearray(b"\xbe\xef")


def test_a_frame_on_one_of_several_readers_is_received():
    transceiver, readers = _receiving(2)
    readers[1].load(_aura_pulses(b"\x11\x22"))

    transceiver.update(0.0)

    assert transceiver.received == bytearray(b"\x11\x22")


def test_back_to_back_frames_on_one_reader_are_received_one_update_apart():
    transceiver, readers = _receiving(1)
    readers[0].load(_aura_pulses(b"\x01") + _aura_pulses(b"\x02"))

    transceiver.update(0.0)
    first = transceiver.received
    transceiver.update(0.0)

    assert first == bytearray(b"\x01")
    assert transceiver.received == bytearray(b"\x02")


# ---------------------------------------------------------------------------
# IR multi-receiver — lowest error margin wins
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("clean_index", [0, 1])
def test_the_frame_with_the_lowest_error_margin_wins_and_its_reader_is_named(clean_index):
    noisy = _aura_pulses(b"\xab")
    noisy[3] += 80  # 80 µs deviation — still within the decoder's tolerance
    transceiver, readers = _receiving(2)
    readers[clean_index].load(_aura_pulses(b"\xab"))
    readers[1 - clean_index].load(noisy)

    transceiver.update(0.0)

    assert transceiver.received == bytearray(b"\xab")
    assert transceiver.last_error_margin == 0
    assert transceiver.last_best_receiver is readers[clean_index]


def test_the_first_reader_wins_an_error_margin_tie():
    transceiver, readers = _receiving(3)
    readers[1].load(_aura_pulses(b"\x5a"))
    readers[2].load(_aura_pulses(b"\x5a"))

    transceiver.update(0.0)

    assert transceiver.last_best_receiver is readers[1]


def test_the_winning_readers_signal_is_reported():
    transceiver, readers = _receiving(3)
    readers[2].load(_aura_pulses(b"\x99"))

    transceiver.update(0.0)

    assert transceiver.last_signal_strength == 1.0
    assert transceiver.last_error_margin == 0
    assert transceiver.last_best_receiver is readers[2]


def test_a_single_reader_reports_its_signal_but_names_no_best_receiver():
    """With one reader there is no pick to report, but the signal still is."""
    transceiver, readers = _receiving(1)
    readers[0].load(_aura_pulses(b"\x42"))

    transceiver.update(0.0)

    assert transceiver.last_signal_strength == 1.0
    assert transceiver.last_best_receiver is None


def test_no_signal_or_best_receiver_is_reported_before_the_first_frame():
    transceiver, _ = _receiving(2)

    transceiver.update(0.0)

    assert transceiver.last_signal_strength is None
    assert transceiver.last_error_margin is None
    assert transceiver.last_best_receiver is None


# ---------------------------------------------------------------------------
# Drain-but-discard while emitting
# ---------------------------------------------------------------------------


def test_frames_read_on_any_reader_while_emitting_are_never_received():
    transceiver, readers, _ = _emitting(3, holds=True)
    transceiver.send(b"\x33", LINE)  # the writer stays busy: still emitting
    readers[0].load(_aura_pulses(b"\x33"))
    readers[2].load(_aura_pulses(b"\x33"))

    transceiver.update(0.0)

    assert transceiver.received is None


def test_pulses_read_while_emitting_count_as_dropped_not_seen():
    transceiver, readers, _ = _emitting(2, holds=True)
    transceiver.send(b"\x33", LINE)
    readers[0].load([100, 200])
    readers[1].load([300, 400, 500])

    transceiver.update(0.0)

    counters = _counters(transceiver)
    assert counters["pulses_dropped_transmitting"] == 5
    assert counters["pulses_seen"] == 0


def test_the_first_update_after_emission_ends_drains_the_buffered_echo_tail():
    transceiver, readers, _ = _emitting(2, holds=False)
    transceiver.send(b"\x33", LINE)  # the blocking write ends inside send
    readers[0].load([111, 222])  # echo tail still buffered in the reader

    transceiver.update(0.0)

    assert _counters(transceiver)["pulses_dropped_transmitting"] == 2


def test_a_frame_after_the_post_emission_drain_is_received_normally():
    transceiver, readers, _ = _emitting(2, holds=False)
    transceiver.send(b"\x33", LINE)
    transceiver.update(0.0)  # the one post-emission drain
    readers[1].load(_aura_pulses(b"\x21"))

    transceiver.update(0.0)

    assert transceiver.received == bytearray(b"\x21")


def test_a_decode_in_progress_on_every_reader_when_emission_begins_is_reset():
    pulses = _aura_pulses(b"\x44")
    mid = len(pulses) // 2
    transceiver, readers, writer = _emitting(2, holds=True)
    for reader in readers:
        reader.load(pulses[:mid])
    transceiver.update(0.0)  # both readers mid-decode

    transceiver.send(b"\x01", LINE)
    transceiver.update(0.0)  # drains with nothing buffered — still resets
    writer.finish()
    transceiver.update(0.0)  # emission ends; the post-emission drain
    for reader in readers:
        reader.load(pulses[mid:])
    transceiver.update(0.0)

    assert transceiver.received is None


def test_a_decode_in_progress_when_emission_ends_does_not_survive_the_post_emission_drain():
    pulses = _aura_pulses(b"\xde\xad")
    mid = len(pulses) // 2
    transceiver, readers, writer = _emitting(1, holds=True)
    transceiver.send(b"\x01", LINE)
    readers[0].load(pulses[:mid])  # captured while emitting
    transceiver.update(0.0)

    writer.finish()
    transceiver.update(0.0)  # emission ends; the post-emission drain
    readers[0].load(pulses[mid:])
    transceiver.update(0.0)

    assert transceiver.received is None


# ---------------------------------------------------------------------------
# Codec swaps
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("reader_count", [1, 2])
def test_after_apply_codec_frames_decode_with_the_new_wire_frame(reader_count):
    transceiver, readers = _receiving(reader_count)

    transceiver.apply_codec(TagInfraredEncoder, TagInfraredDecoder)
    readers[-1].load(_tag_pulses(b"\x10"))
    transceiver.update(0.0)

    assert transceiver.received == bytearray(b"\x10")


def test_apply_codec_builds_a_separate_decoder_for_each_reader():
    built: list[TagInfraredDecoder] = []

    def decoder_factory() -> TagInfraredDecoder:
        decoder = TagInfraredDecoder()
        built.append(decoder)
        return decoder

    transceiver, _ = _receiving(2)

    transceiver.apply_codec(TagInfraredEncoder, decoder_factory)

    assert len(built) == 2
    assert built[0] is not built[1]


def test_a_partial_frame_on_one_reader_does_not_corrupt_another_readers_frame():
    pulses = _tag_pulses(b"\x30")
    transceiver, readers = _receiving(2)
    transceiver.apply_codec(TagInfraredEncoder, TagInfraredDecoder)
    readers[0].load(pulses[: len(pulses) // 2])  # never completes
    transceiver.update(0.0)

    readers[1].load(pulses)
    transceiver.update(0.0)

    assert transceiver.received == bytearray(b"\x30")


def test_after_apply_codec_telemetry_reports_the_new_decoders_counters():
    bad_preamble = list(TAG_PREAMBLE)
    bad_preamble[1] = 4000  # invalid but below the inter-frame gap threshold
    transceiver, readers = _receiving(1)
    transceiver.apply_codec(TagInfraredEncoder, TagInfraredDecoder)
    readers[0].load(bad_preamble)

    transceiver.update(0.0)

    assert _counters(transceiver)["preamble_reject"] == 1


# ---------------------------------------------------------------------------
# Inter-frame gap
# ---------------------------------------------------------------------------


def test_an_inter_frame_gap_abandons_a_stalled_partial_frame_so_the_next_decodes():
    stalled = _tag_pulses(b"\x55")[: len(TAG_PREAMBLE) + 2]
    transceiver, readers = _receiving(1)
    transceiver.apply_codec(TagInfraredEncoder, TagInfraredDecoder)

    readers[0].load(stalled + [TAG_GAP_THRESHOLD] + _tag_pulses(b"\x2a"))
    transceiver.update(0.0)

    assert transceiver.received == bytearray(b"\x2a")


# ---------------------------------------------------------------------------
# IR receive-path telemetry
# ---------------------------------------------------------------------------


def test_telemetry_line_reports_on_its_first_call():
    transceiver, _ = _receiving(1)

    assert transceiver.telemetry_line() is not None


def test_telemetry_line_is_none_until_a_counter_changes():
    transceiver, readers = _receiving(1)
    transceiver.telemetry_line()
    transceiver.update(0.0)
    unchanged = transceiver.telemetry_line()

    readers[0].load([100])
    transceiver.update(0.0)

    assert unchanged is None
    assert transceiver.telemetry_line() is not None


def test_telemetry_line_reports_every_counter_in_pipeline_order_after_a_frame():
    pulses = _aura_pulses(b"\x42")
    transceiver, readers = _receiving(1)
    readers[0].load(pulses)

    transceiver.update(0.0)

    assert transceiver.telemetry_line() == (
        "ir: pulses_seen=" + str(len(pulses)) + " buffer_full_on_poll=0 "
        "packets_started=0 preamble_reject=0 mark_reject=0 space_reject=0 "
        "packets_completed=0 packets_surfaced=1 pulses_dropped_transmitting=0"
    )


def test_pulses_seen_counts_every_pulse_across_readers_and_updates():
    transceiver, readers = _receiving(2)
    readers[0].load([100, 200])
    readers[1].load([300])
    transceiver.update(0.0)
    readers[0].load([400])
    transceiver.update(0.0)

    assert _counters(transceiver)["pulses_seen"] == 4


def test_packets_surfaced_counts_only_received_frames():
    transceiver, readers = _receiving(2)
    readers[0].load(_aura_pulses(b"\x01"))
    transceiver.update(0.0)
    readers[1].load([100, 200])  # noise, no frame
    transceiver.update(0.0)

    assert _counters(transceiver)["packets_surfaced"] == 1


def test_decoder_counters_are_summed_across_readers():
    bad_preamble = list(TAG_PREAMBLE)
    bad_preamble[1] = 4000  # invalid but below the inter-frame gap threshold
    transceiver, readers = _receiving(2)
    transceiver.apply_codec(TagInfraredEncoder, TagInfraredDecoder)
    readers[0].load(bad_preamble)
    readers[1].load(bad_preamble)

    transceiver.update(0.0)

    assert _counters(transceiver)["preamble_reject"] == 2


def test_reader_counters_are_summed_across_readers():
    transceiver, readers = _receiving(3)
    readers[0].buffer_full_on_poll = 2
    readers[2].buffer_full_on_poll = 5

    assert _counters(transceiver)["buffer_full_on_poll"] == 7


def test_packets_completed_can_exceed_surfaced_when_several_readers_catch_one_shot():
    """Dedup, not loss: each reader's decoder completes the same shot, but
    only the winner is received."""
    transceiver, readers = _receiving(3)
    transceiver.apply_codec(TagInfraredEncoder, TagInfraredDecoder)
    readers[0].load(_tag_pulses(b"\x10"))
    readers[2].load(_tag_pulses(b"\x10"))

    transceiver.update(0.0)

    counters = _counters(transceiver)
    assert counters["packets_completed"] == 2
    assert counters["packets_surfaced"] == 1


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
    """An ``IrTelemetrySnapshot.__init__`` with ``pulses_seen`` and
    ``packets_surfaced`` swapped relative to ``FIELDS`` — a stand-in for a
    future ``FIELDS`` reorder."""
    self.pulses_seen = pulses_seen
    self.packets_surfaced = packets_surfaced
    self.buffer_full_on_poll = buffer_full_on_poll
    self.packets_started = packets_started
    self.preamble_reject = preamble_reject
    self.mark_reject = mark_reject
    self.space_reject = space_reject
    self.packets_completed = packets_completed
    self.pulses_dropped_transmitting = pulses_dropped_transmitting


def test_telemetry_counters_survive_a_snapshot_fields_reorder(monkeypatch):
    """Counters reach the snapshot by name, so reordering its fields swaps nothing."""
    monkeypatch.setattr(IrTelemetrySnapshot, "__init__", _reordered_snapshot_init)
    pulses = _aura_pulses(b"\xde\xad")
    transceiver, readers = _receiving(1)
    readers[0].load(pulses)

    transceiver.update(0.0)

    counters = _counters(transceiver)
    assert counters["pulses_seen"] == len(pulses)
    assert counters["packets_surfaced"] == 1


def _ir_allocations_over_100_updates(transceiver: InfraredTransceiver) -> list:
    """The IR modules' allocation growth across 100 ``update`` calls.

    Snapshot comparison catches transient per-tick allocations too; only
    allocations in the IR transport and transceiver modules count, which
    filters out tracemalloc's own overhead.
    """
    for _ in range(5):  # let one-time setup allocations settle
        transceiver.update(0.0)

    tracemalloc.start()
    before = tracemalloc.take_snapshot()
    for _ in range(100):
        transceiver.update(0.0)
    after = tracemalloc.take_snapshot()
    tracemalloc.stop()

    return [
        stat
        for stat in after.compare_to(before, "lineno")
        if stat.traceback[0].filename.endswith(("/ir_transport.py", "/ir_transceiver.py"))
        and stat.size_diff > 0
    ]


@pytest.mark.parametrize("reader_count", [1, 3])
def test_update_allocates_nothing_when_no_pulse_arrives(reader_count):
    transceiver, _ = _receiving(reader_count)

    diff = _ir_allocations_over_100_updates(transceiver)

    assert not diff, f"Unexpected per-tick allocations: {diff}"


def test_update_allocates_nothing_while_draining_during_emission():
    """Readers stay empty, so only the drain loop and the emission check
    repeat — a growing counter's own int widening would be a false positive."""
    transceiver, _, _ = _emitting(3, holds=True)
    transceiver.send(b"\x01", LINE)

    diff = _ir_allocations_over_100_updates(transceiver)

    assert not diff, f"Unexpected per-tick allocations: {diff}"


# ---------------------------------------------------------------------------
# No readers
# ---------------------------------------------------------------------------


def test_a_transceiver_with_no_readers_receives_nothing_and_reports_no_receive_values():
    transceiver = InfraredTransceiver([], {LINE: "GP1"}, EmitterWriterFactory())

    transceiver.update(0.0)

    assert transceiver.receives is False
    assert transceiver.received is None
    assert transceiver.last_signal_strength is None
    assert transceiver.last_error_margin is None
    assert transceiver.last_best_receiver is None
    assert transceiver.telemetry_line() is None
