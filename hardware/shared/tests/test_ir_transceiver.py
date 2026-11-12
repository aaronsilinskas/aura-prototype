"""Behaviour-driven tests for InfraredTransceiver (hardware/shared/ir_transceiver.py)."""

import pytest

from engine.network import AREA_OF_EFFECT, CONE, LINE
from hardware.shared.ir_codecs.aura import AuraInfraredDecoder, AuraInfraredEncoder
from hardware.shared.ir_codecs.tag import TagInfraredDecoder, TagInfraredEncoder
from hardware.shared.ir_transceiver import InfraredTransceiver
from hardware.shared.ir_transport import PulseReader, PulseWriter
from hardware.shared.tests.ir_fakes import RecordingPulseWriter

# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class ControllableFakePulseWriter(PulseWriter):
    """Non-blocking fake writer whose busy state the test drives directly."""

    def __init__(self) -> None:
        self.calls: list = []
        self._busy = False

    def write_pulses(self, durations) -> None:
        self.calls.append(list(durations))
        self._busy = True

    def is_busy(self) -> bool:
        return self._busy

    def set_busy(self, busy: bool) -> None:
        self._busy = busy


class FakePulseReader(PulseReader):
    """Replaying fake — drains a queue of pre-loaded pulses one at a time."""

    def __init__(self, pulses=None) -> None:
        self._queue = list(pulses) if pulses else []

    def load(self, pulses) -> None:
        """Replace the pending pulse queue."""
        self._queue = list(pulses)

    def read_pulse(self) -> int | None:
        if self._queue:
            return self._queue.pop(0)
        return None


def _encode_pulses(payload: bytes | bytearray) -> list[int]:
    return list(AuraInfraredEncoder().encode(bytes(payload)))


def _transceiver_over(
    readers: list[FakePulseReader] | None = None,
    writers: dict[str, PulseWriter] | None = None,
) -> InfraredTransceiver:
    """A transceiver built over *readers*, wiring each emitter in *writers* to that writer."""
    wired = writers or {}
    return InfraredTransceiver.build(
        list(readers or []),
        {emitter: emitter for emitter in wired},
        lambda emitter, _pin: (wired[emitter], "fake"),
    )


def _counter(line: str | None, name: str) -> int:
    """Read one ``name=N`` counter out of a telemetry line."""
    assert line is not None
    for part in line.split():
        key, _, value = part.partition("=")
        if key == name:
            return int(value)
    raise AssertionError(f"{name} not in {line!r}")


class _WriterFactory:
    """Builds a writer per emitter, recording each ``(emitter, pin)`` call.

    Each writer is a blocking :class:`RecordingPulseWriter`, or, with
    *echo_to*, one that also lands its pulses on those readers like a lit
    emitter's self-echo.
    """

    def __init__(self, kind: str = "fake", echo_to: list[FakePulseReader] | None = None) -> None:
        self.kind = kind
        self.calls: list[tuple[str, object]] = []
        self.writers: dict[str, RecordingPulseWriter] = {}
        self._echo_to = echo_to or []

    def __call__(self, emitter: str, pin: object) -> tuple[PulseWriter, str]:
        self.calls.append((emitter, pin))
        writer = _EchoingPulseWriter(self._echo_to)
        self.writers[emitter] = writer
        return writer, self.kind


class _EchoingPulseWriter(RecordingPulseWriter):
    """A blocking recording writer whose pulses also land on *echo_to*'s readers."""

    def __init__(self, echo_to: list[FakePulseReader]) -> None:
        super().__init__()
        self._echo_to = echo_to

    def write_pulses(self, durations) -> None:
        super().write_pulses(durations)
        for reader in self._echo_to:
            reader.load(durations)


_ALL_PINS = {LINE: "GP1", CONE: "GP2", AREA_OF_EFFECT: "GP3"}


# ---------------------------------------------------------------------------
# build() — wires itself from pulse readers, emitter pins and a writer factory
# ---------------------------------------------------------------------------


def test_build_calls_the_factory_once_per_emitter_in_ir_emitters_order_with_its_pin() -> None:
    factory = _WriterFactory()
    pins = {AREA_OF_EFFECT: object(), LINE: object(), CONE: object()}

    transceiver = InfraredTransceiver.build([FakePulseReader()], pins, factory)

    assert factory.calls == [
        (LINE, pins[LINE]),
        (CONE, pins[CONE]),
        (AREA_OF_EFFECT, pins[AREA_OF_EFFECT]),
    ]
    assert transceiver.emitters == (LINE, CONE, AREA_OF_EFFECT)


def test_build_reports_the_writer_kind_the_factory_produced() -> None:
    transceiver = InfraredTransceiver.build(
        [FakePulseReader()], {LINE: "GP1"}, _WriterFactory(kind="pio")
    )

    assert transceiver.writer_kind == "pio"


def test_build_with_no_emitter_pins_wires_no_emitter_and_reports_no_writer_kind() -> None:
    factory = _WriterFactory()

    transceiver = InfraredTransceiver.build([FakePulseReader()], {}, factory)

    assert factory.calls == []
    assert transceiver.emitters == ()
    assert transceiver.writer_kind is None


@pytest.mark.parametrize("emitter", [LINE, CONE, AREA_OF_EFFECT])
def test_build_sends_only_on_the_writer_built_for_that_emitter_in_the_aura_wire_frame(
    emitter,
) -> None:
    factory = _WriterFactory()
    transceiver = InfraredTransceiver.build([FakePulseReader()], _ALL_PINS, factory)

    transceiver.send(b"\x2a", emitter)

    assert {e: w.calls for e, w in factory.writers.items()} == {
        e: [_encode_pulses(b"\x2a")] if e == emitter else [] for e in _ALL_PINS
    }


def test_build_does_not_wire_an_emitter_missing_from_the_pins() -> None:
    transceiver = InfraredTransceiver.build([FakePulseReader()], {LINE: "GP1"}, _WriterFactory())

    assert transceiver.emitters == (LINE,)
    with pytest.raises(ValueError):
        transceiver.send(b"\x2a", CONE)


def test_build_with_no_readers_wires_no_receiver() -> None:
    transceiver = InfraredTransceiver.build([], {LINE: "GP1"}, _WriterFactory())

    transceiver.update(0.0)

    assert transceiver.receives is False
    assert transceiver.received is None


@pytest.mark.parametrize("reader_count", [1, 3])
def test_build_receives_an_aura_shot_landing_on_its_readers(reader_count) -> None:
    readers = [FakePulseReader(_encode_pulses(b"\x2a")) for _ in range(reader_count)]
    transceiver = InfraredTransceiver.build(list(readers), {}, _WriterFactory())

    transceiver.update(0.0)

    assert transceiver.receives is True
    assert transceiver.received == bytearray(b"\x2a")
    assert transceiver.codec == (AuraInfraredEncoder, AuraInfraredDecoder)


def test_build_receives_on_every_reader_not_just_the_first() -> None:
    readers = [FakePulseReader(), FakePulseReader(_encode_pulses(b"\x2a"))]
    transceiver = InfraredTransceiver.build(list(readers), {}, _WriterFactory())

    transceiver.update(0.0)

    assert transceiver.received == bytearray(b"\x2a")


@pytest.mark.parametrize("emitter", [LINE, CONE, AREA_OF_EFFECT])
def test_build_shares_one_gate_so_no_reader_decodes_a_send_on_any_emitter(
    emitter,
) -> None:
    readers = [FakePulseReader(), FakePulseReader()]
    transceiver = InfraredTransceiver.build(
        list(readers), _ALL_PINS, _WriterFactory(echo_to=readers)
    )

    transceiver.send(b"\x2a", emitter)
    transceiver.update(0.0)

    assert transceiver.received is None


# ---------------------------------------------------------------------------
# send() — raises for an emitter that isn't wired
# ---------------------------------------------------------------------------


def test_send_raises_with_no_emitter_wired() -> None:
    transceiver = _transceiver_over()

    with pytest.raises(ValueError):
        transceiver.send(b"x", LINE)


def test_transceiver_does_not_expose_transmitters_as_a_public_collection() -> None:
    transceiver = _transceiver_over(writers={LINE: RecordingPulseWriter()})

    assert not hasattr(transceiver, "transmitters")


# ---------------------------------------------------------------------------
# busy() — reports and pumps one emitter
# ---------------------------------------------------------------------------


def test_busy_reports_an_emitter_whose_writer_is_still_writing() -> None:
    writer = ControllableFakePulseWriter()
    transceiver = _transceiver_over(writers={LINE: writer})

    transceiver.send(b"\xab", LINE)

    assert transceiver.busy(LINE) is True


def test_busy_reports_idle_once_the_writer_finishes() -> None:
    writer = ControllableFakePulseWriter()
    transceiver = _transceiver_over(writers={LINE: writer})
    transceiver.send(b"\xab", LINE)

    writer.set_busy(False)

    assert transceiver.busy(LINE) is False


def test_busy_reports_idle_for_a_blocking_writer() -> None:
    transceiver = _transceiver_over(writers={LINE: RecordingPulseWriter()})

    transceiver.send(b"\xab", LINE)

    assert transceiver.busy(LINE) is False


def test_busy_starts_only_that_emitters_queued_send_once_its_writer_finishes() -> None:
    line_writer = ControllableFakePulseWriter()
    cone_writer = ControllableFakePulseWriter()
    transceiver = _transceiver_over(writers={LINE: line_writer, CONE: cone_writer})
    for emitter in (LINE, CONE):
        transceiver.send(b"\x01", emitter)
        transceiver.send(b"\x02", emitter)  # queued behind the write in flight
    line_writer.set_busy(False)
    cone_writer.set_busy(False)

    transceiver.busy(LINE)

    assert line_writer.calls == [_encode_pulses(b"\x01"), _encode_pulses(b"\x02")]
    assert cone_writer.calls == [_encode_pulses(b"\x01")]


def test_busy_raises_for_unwired_emitter() -> None:
    transceiver = _transceiver_over(writers={LINE: RecordingPulseWriter()})

    with pytest.raises(ValueError):
        transceiver.busy(CONE)


# ---------------------------------------------------------------------------
# update() — pumps every transmitter, then receives
# ---------------------------------------------------------------------------


def test_update_releases_a_write_that_finished_this_tick_before_receiving() -> None:
    """Pumping first lets the falling-edge flush land on this tick, so the
    very next tick's frame decodes instead of being discarded as self-echo."""
    writer = ControllableFakePulseWriter()
    reader = FakePulseReader()
    transceiver = _transceiver_over([reader], {LINE: writer})
    transceiver.send(b"\xaa", LINE)
    writer.set_busy(False)

    transceiver.update(0.0)
    reader.load(_encode_pulses(b"\x07"))
    transceiver.update(0.0)

    assert transceiver.received == bytearray(b"\x07")


@pytest.mark.parametrize("reader_count", [0, 1])
def test_update_starts_every_emitters_queued_send_once_its_writer_finishes(
    reader_count,
) -> None:
    writers = {LINE: ControllableFakePulseWriter(), CONE: ControllableFakePulseWriter()}
    transceiver = _transceiver_over([FakePulseReader() for _ in range(reader_count)], dict(writers))
    for emitter, writer in writers.items():
        transceiver.send(b"\x01", emitter)
        transceiver.send(b"\x02", emitter)  # queued behind the write in flight
        writer.set_busy(False)

    transceiver.update(0.0)

    assert {e: w.calls for e, w in writers.items()} == {
        e: [_encode_pulses(b"\x01"), _encode_pulses(b"\x02")] for e in writers
    }


def test_update_with_nothing_wired_leaves_received_none() -> None:
    transceiver = _transceiver_over()

    transceiver.update(0.0)  # must not raise

    assert transceiver.received is None


# ---------------------------------------------------------------------------
# received — set only on a decoding tick
# ---------------------------------------------------------------------------


def test_received_is_none_when_the_pulses_decode_nothing() -> None:
    transceiver = _transceiver_over([FakePulseReader([100, 200])])

    transceiver.update(0.0)

    assert transceiver.received is None


def test_received_holds_the_decoded_payload_on_a_decoding_tick() -> None:
    payload = bytearray(b"\xab\xcd")
    transceiver = _transceiver_over([FakePulseReader(_encode_pulses(payload))])

    transceiver.update(0.0)

    assert transceiver.received == payload


def test_received_resets_to_none_on_the_tick_after_a_decode() -> None:
    transceiver = _transceiver_over([FakePulseReader(_encode_pulses(b"\x01"))])

    transceiver.update(0.0)
    transceiver.update(0.0)

    assert transceiver.received is None


# ---------------------------------------------------------------------------
# apply_codec()
# ---------------------------------------------------------------------------


def test_apply_codec_makes_every_emitter_send_in_the_new_wire_frame() -> None:
    writers = {LINE: RecordingPulseWriter(), CONE: RecordingPulseWriter()}
    transceiver = _transceiver_over([FakePulseReader()], dict(writers))

    transceiver.apply_codec(TagInfraredEncoder, TagInfraredDecoder)
    transceiver.send(b"\x10", LINE)
    transceiver.send(b"\x10", CONE)

    tag_pulses = list(TagInfraredEncoder().encode(b"\x10"))
    assert {e: w.calls for e, w in writers.items()} == {LINE: [tag_pulses], CONE: [tag_pulses]}


def test_apply_codec_makes_the_readers_decode_the_new_wire_frame() -> None:
    """A Tag frame only decodes once the Tag decoder is installed."""
    payload = bytearray([0x10])
    transceiver = _transceiver_over([FakePulseReader(TagInfraredEncoder().encode(payload))])

    transceiver.apply_codec(TagInfraredEncoder, TagInfraredDecoder)
    transceiver.update(0.0)

    assert transceiver.received == payload


def test_apply_codec_with_no_receiver_wired_still_changes_what_is_sent() -> None:
    writer = RecordingPulseWriter()
    transceiver = _transceiver_over(writers={LINE: writer})

    transceiver.apply_codec(TagInfraredEncoder, TagInfraredDecoder)  # must not raise
    transceiver.send(b"\x10", LINE)

    assert writer.calls == [list(TagInfraredEncoder().encode(b"\x10"))]


def test_apply_codec_is_a_safe_noop_with_nothing_wired() -> None:
    transceiver = _transceiver_over()

    transceiver.apply_codec(TagInfraredEncoder, TagInfraredDecoder)  # must not raise


# ---------------------------------------------------------------------------
# codec — the installed class pair, read back
# ---------------------------------------------------------------------------


def test_codec_is_the_aura_pair_before_any_codec_is_applied() -> None:
    transceiver = _transceiver_over()

    assert transceiver.codec == (AuraInfraredEncoder, AuraInfraredDecoder)


def test_codec_reads_back_the_class_pair_apply_codec_took() -> None:
    transceiver = _transceiver_over()

    transceiver.apply_codec(TagInfraredEncoder, TagInfraredDecoder)

    assert transceiver.codec == (TagInfraredEncoder, TagInfraredDecoder)


def test_codec_cannot_be_assigned() -> None:
    transceiver = _transceiver_over()

    with pytest.raises(AttributeError):
        transceiver.codec = (TagInfraredEncoder, TagInfraredDecoder)  # type: ignore[misc]  # proves it is read-only


# ---------------------------------------------------------------------------
# Receive-side values: signal strength, error margin, best receiver, telemetry
# ---------------------------------------------------------------------------


def test_a_cleanly_timed_frame_reports_full_signal_strength() -> None:
    transceiver = _transceiver_over([FakePulseReader(_encode_pulses(b"\x42"))])

    transceiver.update(0.0)

    assert transceiver.last_signal_strength == 1.0


def test_a_cleanly_timed_frame_reports_a_zero_error_margin() -> None:
    transceiver = _transceiver_over([FakePulseReader(_encode_pulses(b"\x42"))])

    transceiver.update(0.0)

    assert transceiver.last_error_margin == 0


def test_signal_strength_and_error_margin_are_none_before_any_frame() -> None:
    transceiver = _transceiver_over([FakePulseReader()])

    transceiver.update(0.0)

    assert (transceiver.last_signal_strength, transceiver.last_error_margin) == (None, None)


def test_last_best_receiver_names_the_reader_that_decoded_the_frame() -> None:
    readers = [FakePulseReader(), FakePulseReader(_encode_pulses(b"\x42"))]
    transceiver = _transceiver_over(readers)

    transceiver.update(0.0)

    assert transceiver.last_best_receiver is readers[1]


def test_last_best_receiver_is_none_with_a_single_reader() -> None:
    transceiver = _transceiver_over([FakePulseReader(_encode_pulses(b"\x42"))])

    transceiver.update(0.0)

    assert transceiver.last_best_receiver is None


def test_telemetry_line_reports_a_decoded_frame_through_every_stage() -> None:
    """Uses the Tag codec because its decoder counts started and completed packets."""
    pulses = list(TagInfraredEncoder().encode(b"\x10"))
    transceiver = _transceiver_over([FakePulseReader(pulses)])
    transceiver.apply_codec(TagInfraredEncoder, TagInfraredDecoder)

    transceiver.update(0.0)

    assert transceiver.telemetry_line() == (
        f"ir: pulses_seen={len(pulses)} buffer_full_on_poll=0 packets_started=1"
        " preamble_reject=0 mark_reject=0 space_reject=0 packets_completed=1"
        " packets_surfaced=1 pulses_dropped_transmitting=0"
    )


def test_telemetry_line_is_none_when_no_counter_changed() -> None:
    transceiver = _transceiver_over([FakePulseReader(_encode_pulses(b"\x42"))])
    transceiver.update(0.0)
    transceiver.telemetry_line()

    transceiver.update(0.0)

    assert transceiver.telemetry_line() is None


def test_with_no_receiver_wired_every_receive_side_value_is_none() -> None:
    transceiver = _transceiver_over(writers={LINE: RecordingPulseWriter()})

    transceiver.update(0.0)

    assert transceiver.receives is False
    assert (
        transceiver.last_signal_strength,
        transceiver.last_error_margin,
        transceiver.last_best_receiver,
        transceiver.telemetry_line(),
    ) == (None, None, None, None)


# ---------------------------------------------------------------------------
# Full self-echo suppression cycle, driven entirely through update()
# ---------------------------------------------------------------------------


def test_update_discards_self_echo_and_an_overlapping_real_shot_while_transmitting() -> None:
    """A transmit arms the gate; while it stays armed, update() drains and
    discards both the self-echo and any real shot overlapping it — the two
    are indistinguishable at the pulse level, so both are dropped."""
    reader = FakePulseReader()
    transceiver = _transceiver_over([reader], {LINE: ControllableFakePulseWriter()})

    transceiver.send(b"\xaa", LINE)  # non-blocking writer stays busy — gate armed across ticks
    echo_pulses = _encode_pulses(b"\xaa")
    overlapping_shot_pulses = _encode_pulses(b"\xbb")
    reader.load(echo_pulses + overlapping_shot_pulses)

    transceiver.update(0.0)

    assert transceiver.received is None
    assert _counter(transceiver.telemetry_line(), "pulses_dropped_transmitting") == (
        len(echo_pulses) + len(overlapping_shot_pulses)
    )


def test_update_falling_edge_flush_recovers_the_decoder_for_the_next_genuine_packet() -> None:
    """After the transmit ends, one more update() drain-discards the flush
    tail; the decoder returns to idle and the next real packet decodes
    normally — the inter-frame-gap recovery path."""
    writer = ControllableFakePulseWriter()
    reader = FakePulseReader()
    transceiver = _transceiver_over([reader], {LINE: writer})

    transceiver.send(b"\xaa", LINE)  # gate armed
    reader.load(_encode_pulses(b"\xaa"))  # self-echo captured while transmitting
    transceiver.update(0.0)
    assert transceiver.received is None
    dropped_while_transmitting = _counter(
        transceiver.telemetry_line(), "pulses_dropped_transmitting"
    )

    writer.set_busy(False)  # hardware signals the write completed
    reader.load([111])  # buffered echo tail still sitting in the reader
    transceiver.update(0.0)  # releases the gate; falling-edge flush drains the tail
    assert transceiver.received is None
    assert (
        _counter(transceiver.telemetry_line(), "pulses_dropped_transmitting")
        == dropped_while_transmitting + 1
    )

    payload = b"\x07"
    reader.load(_encode_pulses(payload))
    transceiver.update(0.0)  # gate now fully idle — decodes normally

    assert transceiver.received == bytearray(payload)
