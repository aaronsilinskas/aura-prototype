"""Behaviour-driven tests for InfraredTransceiver (hardware/shared/ir_transceiver.py)."""

import pytest

from engine.network import AREA_OF_EFFECT, CONE, LINE
from hardware.shared.ir_codecs.aura import AuraInfraredDecoder, AuraInfraredEncoder
from hardware.shared.ir_codecs.base import InfraredEncoder
from hardware.shared.ir_codecs.tag import TagInfraredDecoder, TagInfraredEncoder
from hardware.shared.ir_telemetry import format_ir_telemetry_line
from hardware.shared.ir_transceiver import InfraredTransceiver
from hardware.shared.ir_transport import (
    InfraredReceiver,
    InfraredTransmitter,
    IrTransmitGate,
    PulseReader,
    PulseWriter,
)
from hardware.shared.tests.ir_fakes import RecordingPulseWriter, StubEncoder, make_transmitter

# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class _RecordingTransmitter(InfraredTransmitter):
    """Fake transmitter recording each poll() call into a shared order list —
    isolates update()'s pump-before-receive fan-out from InfraredTransmitter's
    own poll() behaviour (covered separately in test_ir_transport.py)."""

    def __init__(self, calls: list) -> None:
        self._calls = calls

    def poll(self) -> bool:
        self._calls.append("poll")
        return False

    def send(self, data: bytes) -> bool:
        return True  # not exercised by these tests

    def set_encoder(self, encoder: InfraredEncoder) -> None:
        pass  # not exercised by these tests


class _RecordingSetEncoderTransmitter(InfraredTransmitter):
    """Fake transmitter recording each set_encoder() call and its argument."""

    def __init__(self, calls: list) -> None:
        self._calls = calls

    def poll(self) -> bool:
        return False  # not exercised by these tests

    def send(self, data: bytes) -> bool:
        return True  # not exercised by these tests

    def set_encoder(self, encoder: InfraredEncoder) -> None:
        self._calls.append(encoder)


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


class _RecordingPulseReader(PulseReader):
    """Records each read_pulse() call into a shared order list; never has a pulse."""

    def __init__(self, calls: list) -> None:
        self._calls = calls

    def read_pulse(self) -> int | None:
        self._calls.append("read")
        return None


def _encode_pulses(payload: bytes | bytearray) -> list[int]:
    return list(AuraInfraredEncoder().encode(bytes(payload)))


def _receiver_holding(pulses) -> InfraredReceiver:
    """A real Aura-decoding receiver over one reader preloaded with *pulses*."""
    return InfraredReceiver([FakePulseReader(pulses)], AuraInfraredDecoder)


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
# send() — routes to the named transmitter
# ---------------------------------------------------------------------------


def test_send_routes_payload_to_the_named_transmitter() -> None:
    tx, writer = make_transmitter()
    transceiver = InfraredTransceiver({CONE: tx}, None, IrTransmitGate())

    transceiver.send(b"\xab\xcd", CONE)

    assert writer.calls[0] == [0xAB, 0xCD]


def test_send_routes_to_the_correct_transmitter_among_several() -> None:
    tx_line, writer_line = make_transmitter()
    tx_cone, writer_cone = make_transmitter()
    transceiver = InfraredTransceiver({LINE: tx_line, CONE: tx_cone}, None, IrTransmitGate())

    transceiver.send(b"\xff", CONE)

    assert len(writer_cone.calls) == 1
    assert len(writer_line.calls) == 0


def test_send_raises_for_unwired_emitter() -> None:
    tx, _ = make_transmitter()
    transceiver = InfraredTransceiver({LINE: tx}, None, IrTransmitGate())

    with pytest.raises(ValueError):
        transceiver.send(b"x", CONE)


def test_send_raises_for_empty_transmitter_map() -> None:
    transceiver = InfraredTransceiver({}, None, IrTransmitGate())

    with pytest.raises(ValueError):
        transceiver.send(b"x", LINE)


# ---------------------------------------------------------------------------
# Transmitters are not exposed as a raw collection
# ---------------------------------------------------------------------------


def test_transceiver_does_not_expose_transmitters_as_a_public_collection() -> None:
    tx, _ = make_transmitter()
    transceiver = InfraredTransceiver({LINE: tx}, None, IrTransmitGate())

    assert not hasattr(transceiver, "transmitters")


# ---------------------------------------------------------------------------
# busy() — pumps and reports one emitter's transmitter without exposing the
# transmitter map itself
# ---------------------------------------------------------------------------


def test_busy_pumps_the_named_transmitter() -> None:
    calls: list = []
    transceiver = InfraredTransceiver({LINE: _RecordingTransmitter(calls)}, None, IrTransmitGate())

    transceiver.busy(LINE)

    assert calls == ["poll"]


def test_busy_reports_the_writer_still_in_flight() -> None:
    writer = ControllableFakePulseWriter()
    tx = InfraredTransmitter(writer, StubEncoder())
    transceiver = InfraredTransceiver({LINE: tx}, None, IrTransmitGate())
    tx.send(b"\xab")
    writer.set_busy(True)

    assert transceiver.busy(LINE) is True


def test_busy_reports_the_writer_idle() -> None:
    tx, _ = make_transmitter()
    transceiver = InfraredTransceiver({LINE: tx}, None, IrTransmitGate())

    assert transceiver.busy(LINE) is False


def test_busy_raises_for_unwired_emitter() -> None:
    tx, _ = make_transmitter()
    transceiver = InfraredTransceiver({LINE: tx}, None, IrTransmitGate())

    with pytest.raises(ValueError):
        transceiver.busy(CONE)


# ---------------------------------------------------------------------------
# update() sequencing
# ---------------------------------------------------------------------------


def test_update_pumps_the_transmitter_before_receiving() -> None:
    calls: list = []
    receiver = InfraredReceiver([_RecordingPulseReader(calls)], AuraInfraredDecoder)
    transceiver = InfraredTransceiver(
        {LINE: _RecordingTransmitter(calls)}, receiver, IrTransmitGate()
    )

    transceiver.update(0.0)

    assert calls == ["poll", "read"]


def test_update_polls_every_wired_transmitter() -> None:
    calls: list = []
    transceiver = InfraredTransceiver(
        {LINE: _RecordingTransmitter(calls), CONE: _RecordingTransmitter(calls)},
        None,
        IrTransmitGate(),
    )

    transceiver.update(0.0)

    assert calls == ["poll", "poll"]


def test_update_with_no_receiver_still_polls_transmitters() -> None:
    calls: list = []
    transceiver = InfraredTransceiver({LINE: _RecordingTransmitter(calls)}, None, IrTransmitGate())

    transceiver.update(0.0)

    assert calls == ["poll"]


def test_update_with_no_transmitters_or_receiver_leaves_received_none() -> None:
    transceiver = InfraredTransceiver({}, None, IrTransmitGate())

    transceiver.update(0.0)  # must not raise

    assert transceiver.received is None


# ---------------------------------------------------------------------------
# received — set only on a decoding tick
# ---------------------------------------------------------------------------


def test_received_is_none_when_the_receiver_decodes_nothing() -> None:
    transceiver = InfraredTransceiver({}, _receiver_holding([100, 200]), IrTransmitGate())

    transceiver.update(0.0)

    assert transceiver.received is None


def test_received_holds_the_decoded_payload_on_a_decoding_tick() -> None:
    payload = bytearray(b"\xab\xcd")
    transceiver = InfraredTransceiver(
        {}, _receiver_holding(_encode_pulses(payload)), IrTransmitGate()
    )

    transceiver.update(0.0)

    assert transceiver.received == payload


def test_received_resets_to_none_on_the_tick_after_a_decode() -> None:
    payload = bytearray(b"\x01")
    transceiver = InfraredTransceiver(
        {}, _receiver_holding(_encode_pulses(payload)), IrTransmitGate()
    )

    transceiver.update(0.0)
    transceiver.update(0.0)

    assert transceiver.received is None


# ---------------------------------------------------------------------------
# apply_codec()
# ---------------------------------------------------------------------------


def test_apply_codec_gives_every_transmitter_one_shared_encoder_of_the_given_class() -> None:
    calls: list = []
    transceiver = InfraredTransceiver(
        {
            LINE: _RecordingSetEncoderTransmitter(calls),
            CONE: _RecordingSetEncoderTransmitter(calls),
        },
        None,
        IrTransmitGate(),
    )

    transceiver.apply_codec(TagInfraredEncoder, TagInfraredDecoder)

    line_encoder, cone_encoder = calls
    assert isinstance(line_encoder, TagInfraredEncoder)
    assert cone_encoder is line_encoder


def test_apply_codec_installs_the_decoder_on_the_receiver() -> None:
    """A Tag frame only decodes once the Tag decoder is installed."""
    payload = bytearray([0x10])
    receiver = _receiver_holding(TagInfraredEncoder().encode(payload))
    transceiver = InfraredTransceiver({}, receiver, IrTransmitGate())

    transceiver.apply_codec(TagInfraredEncoder, TagInfraredDecoder)
    transceiver.update(0.0)

    assert transceiver.received == payload


def test_apply_codec_still_fans_out_the_encoder_with_no_receiver_wired() -> None:
    calls: list = []
    transceiver = InfraredTransceiver(
        {LINE: _RecordingSetEncoderTransmitter(calls)}, None, IrTransmitGate()
    )

    transceiver.apply_codec(TagInfraredEncoder, TagInfraredDecoder)  # must not raise

    (encoder,) = calls
    assert isinstance(encoder, TagInfraredEncoder)


def test_apply_codec_is_a_safe_noop_with_no_transmitters_and_no_receiver() -> None:
    transceiver = InfraredTransceiver({}, None, IrTransmitGate())

    transceiver.apply_codec(TagInfraredEncoder, TagInfraredDecoder)  # must not raise


# ---------------------------------------------------------------------------
# codec — the installed class pair, read back
# ---------------------------------------------------------------------------


def test_codec_is_the_aura_pair_before_any_codec_is_applied() -> None:
    transceiver = InfraredTransceiver({}, None, IrTransmitGate())

    assert transceiver.codec == (AuraInfraredEncoder, AuraInfraredDecoder)


def test_codec_reads_back_the_class_pair_apply_codec_took() -> None:
    transceiver = InfraredTransceiver({}, None, IrTransmitGate())

    transceiver.apply_codec(TagInfraredEncoder, TagInfraredDecoder)

    assert transceiver.codec == (TagInfraredEncoder, TagInfraredDecoder)


def test_codec_cannot_be_assigned() -> None:
    transceiver = InfraredTransceiver({}, None, IrTransmitGate())

    with pytest.raises(AttributeError):
        transceiver.codec = (TagInfraredEncoder, TagInfraredDecoder)  # type: ignore[misc]  # proves it is read-only


# ---------------------------------------------------------------------------
# Forwarded telemetry attributes
# ---------------------------------------------------------------------------


def test_last_signal_strength_is_forwarded_from_the_receiver() -> None:
    payload = bytearray(b"\x42")
    reader = FakePulseReader(_encode_pulses(payload))
    receiver = InfraredReceiver([reader], AuraInfraredDecoder)
    transceiver = InfraredTransceiver({}, receiver, IrTransmitGate())

    transceiver.update(0.0)

    assert transceiver.last_signal_strength == receiver.last_signal_strength == 1.0


def test_last_error_margin_is_forwarded_from_the_receiver() -> None:
    payload = bytearray(b"\x42")
    reader = FakePulseReader(_encode_pulses(payload))
    receiver = InfraredReceiver([reader], AuraInfraredDecoder)
    transceiver = InfraredTransceiver({}, receiver, IrTransmitGate())

    transceiver.update(0.0)

    assert transceiver.last_error_margin == receiver.last_error_margin == 0


def test_telemetry_line_is_forwarded_from_the_receiver() -> None:
    payload = bytearray(b"\x42")
    reader = FakePulseReader(_encode_pulses(payload))
    receiver = InfraredReceiver([reader], AuraInfraredDecoder)
    transceiver = InfraredTransceiver({}, receiver, IrTransmitGate())

    transceiver.update(0.0)
    line = transceiver.telemetry_line()

    # Proves forwarding: the transceiver hands back exactly the receiver's own
    # telemetry, rendered through the shared formatter — no re-derivation here.
    assert line == format_ir_telemetry_line(receiver.telemetry())


def test_last_best_receiver_is_forwarded_from_the_receiver() -> None:
    readers: list[PulseReader] = [FakePulseReader(), FakePulseReader(_encode_pulses(b"\x42"))]
    transceiver = InfraredTransceiver(
        {}, InfraredReceiver(readers, AuraInfraredDecoder), IrTransmitGate()
    )

    transceiver.update(0.0)

    assert transceiver.last_best_receiver is readers[1]


def test_last_best_receiver_is_none_with_no_receiver_wired() -> None:
    transceiver = InfraredTransceiver({}, None, IrTransmitGate())
    assert transceiver.last_best_receiver is None


def test_last_signal_strength_is_none_with_no_receiver_wired() -> None:
    transceiver = InfraredTransceiver({}, None, IrTransmitGate())
    assert transceiver.last_signal_strength is None


def test_last_error_margin_is_none_with_no_receiver_wired() -> None:
    transceiver = InfraredTransceiver({}, None, IrTransmitGate())
    assert transceiver.last_error_margin is None


def test_telemetry_line_is_none_with_no_receiver_wired() -> None:
    transceiver = InfraredTransceiver({}, None, IrTransmitGate())
    assert transceiver.telemetry_line() is None


# ---------------------------------------------------------------------------
# Full self-echo suppression cycle, driven entirely through update()
# ---------------------------------------------------------------------------


def test_update_discards_self_echo_and_an_overlapping_real_shot_while_transmitting() -> None:
    """A transmit arms the gate; while it stays armed, update() drains and
    discards both the self-echo and any real shot overlapping it — the two
    are indistinguishable at the pulse level, so both are dropped."""
    gate = IrTransmitGate()
    writer = ControllableFakePulseWriter()
    tx = InfraredTransmitter(writer, AuraInfraredEncoder(), gate)
    reader = FakePulseReader()
    receiver = InfraredReceiver([reader], AuraInfraredDecoder, gate)
    transceiver = InfraredTransceiver({LINE: tx}, receiver, gate)

    tx.send(b"\xaa")  # non-blocking writer stays busy — gate armed across ticks
    echo_pulses = _encode_pulses(b"\xaa")
    overlapping_shot_pulses = _encode_pulses(b"\xbb")
    reader.load(echo_pulses + overlapping_shot_pulses)

    transceiver.update(0.0)

    assert transceiver.received is None
    assert receiver.telemetry().pulses_dropped_transmitting == (
        len(echo_pulses) + len(overlapping_shot_pulses)
    )


def test_update_falling_edge_flush_recovers_the_decoder_for_the_next_genuine_packet() -> None:
    """After the transmit ends, one more update() drain-discards the flush
    tail; the decoder returns to idle and the next real packet decodes
    normally — the inter-frame-gap recovery path."""
    gate = IrTransmitGate()
    writer = ControllableFakePulseWriter()
    tx = InfraredTransmitter(writer, AuraInfraredEncoder(), gate)
    reader = FakePulseReader()
    receiver = InfraredReceiver([reader], AuraInfraredDecoder, gate)
    transceiver = InfraredTransceiver({LINE: tx}, receiver, gate)

    tx.send(b"\xaa")  # gate armed
    reader.load(_encode_pulses(b"\xaa"))  # self-echo captured while transmitting
    transceiver.update(0.0)
    assert transceiver.received is None

    writer.set_busy(False)  # hardware signals the write completed
    reader.load([111])  # buffered echo tail still sitting in the reader
    transceiver.update(0.0)  # releases the gate; falling-edge flush drains the tail
    assert transceiver.received is None
    assert receiver.telemetry().pulses_dropped_transmitting > 0

    payload = b"\x07"
    reader.load(_encode_pulses(payload))
    transceiver.update(0.0)  # gate now fully idle — decodes normally

    assert transceiver.received == bytearray(payload)
