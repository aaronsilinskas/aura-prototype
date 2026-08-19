"""Behaviour-driven tests for InfraredTransceiver (hardware/shared/ir_transceiver.py).

Covers:
- send() routes a payload to the named transmitter, raising ValueError for
  an unknown emitter
- update() pumps every transmitter before it receives, always pumps even
  with no receiver wired, and resets received every tick
- apply_codec() fans the encoder out to every transmitter and installs the
  decoder on the receiver, safely no-op with no transmitters/no receiver
- last_signal_strength / last_error_margin / telemetry_line() forwarded from
  the receiver, and None-safe with no receiver wired
- the full self-echo suppression cycle driven through update(), using fake
  PulseReader/PulseWriter ports wired through the real IrTransmitGate,
  InfraredTransmitter, and InfraredSingleReceiver

Coverage migrated from hardware/shared/tests/test_ir_manager.py, adapted to
InfraredTransceiver owning its transmitters directly rather than reaching
them through an engine.network.TransmitPump seam.
"""

import pytest

from engine.network import CONE, LINE
from hardware.shared.ir_codecs.aura import AuraInfraredDecoder, AuraInfraredEncoder
from hardware.shared.ir_transceiver import InfraredTransceiver
from hardware.shared.ir_transport import (
    InfraredReceiver,
    InfraredSingleReceiver,
    InfraredTransmitter,
    IrTransmitGate,
    PulseReader,
    PulseWriter,
)

# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class _RecordingPulseWriter(PulseWriter):
    """Captures written pulse sequences without touching hardware.

    ``is_busy()`` always reports ``False`` — matches the blocking
    ``PulseOutWriter``'s externally-observable behaviour.
    """

    def __init__(self) -> None:
        self.calls: list[list[int]] = []

    def write_pulses(self, durations) -> None:
        self.calls.append(list(durations))

    def is_busy(self) -> bool:
        return False


class _StubEncoder:
    """Minimal encoder that converts each byte to a single-item pulse list."""

    def encode(self, data: bytes) -> list:
        return list(data)


def _make_transmitter() -> tuple[InfraredTransmitter, _RecordingPulseWriter]:
    writer = _RecordingPulseWriter()
    tx = InfraredTransmitter(writer, _StubEncoder())
    return tx, writer


class _RecordingTransmitter:
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

    def set_encoder(self, encoder) -> None:
        pass  # not exercised by these tests


class _RecordingSetEncoderTransmitter:
    """Fake transmitter recording each set_encoder() call and its argument."""

    def __init__(self, calls: list) -> None:
        self._calls = calls

    def poll(self) -> bool:
        return False  # not exercised by these tests

    def send(self, data: bytes) -> bool:
        return True  # not exercised by these tests

    def set_encoder(self, encoder) -> None:
        self._calls.append(encoder)


class _RecordingReceiver(InfraredReceiver):
    """Records each receive() call into a shared order list; returns nothing."""

    def __init__(self, calls: list) -> None:
        super().__init__()
        self._calls = calls

    def receive(self) -> bytearray | None:
        self._calls.append("receive")
        return None


class _ScriptedReceiver(InfraredReceiver):
    """Returns a pre-scripted sequence of receive() results, one per call."""

    def __init__(self, results: list) -> None:
        super().__init__()
        self._results = list(results)

    def receive(self) -> bytearray | None:
        return self._results.pop(0) if self._results else None


class _RecordingSetDecoderReceiver(InfraredReceiver):
    """Records the decoder installed via set_decoder(); never decodes anything."""

    def __init__(self) -> None:
        super().__init__()
        self.decoder = None

    def receive(self) -> bytearray | None:
        return None  # not exercised by these tests

    def set_decoder(self, decoder) -> None:
        self.decoder = decoder


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


def _encode_pulses(payload: bytes) -> list:
    return list(AuraInfraredEncoder().encode(payload))


# ---------------------------------------------------------------------------
# send() — routes to the named transmitter
# ---------------------------------------------------------------------------


def test_send_routes_payload_to_the_named_transmitter() -> None:
    tx, writer = _make_transmitter()
    transceiver = InfraredTransceiver({CONE: tx}, None, IrTransmitGate())

    transceiver.send(b"\xab\xcd", CONE)

    assert writer.calls[0] == [0xAB, 0xCD]


def test_send_routes_to_the_correct_transmitter_among_several() -> None:
    tx_line, writer_line = _make_transmitter()
    tx_cone, writer_cone = _make_transmitter()
    transceiver = InfraredTransceiver({LINE: tx_line, CONE: tx_cone}, None, IrTransmitGate())

    transceiver.send(b"\xff", CONE)

    assert len(writer_cone.calls) == 1
    assert len(writer_line.calls) == 0


def test_send_raises_for_unwired_emitter() -> None:
    tx, _ = _make_transmitter()
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
    tx, _ = _make_transmitter()
    transceiver = InfraredTransceiver({LINE: tx}, None, IrTransmitGate())

    assert not hasattr(transceiver, "transmitters")


# ---------------------------------------------------------------------------
# update() sequencing
# ---------------------------------------------------------------------------


def test_update_pumps_the_transmitter_before_receiving() -> None:
    calls: list = []
    transceiver = InfraredTransceiver(
        {LINE: _RecordingTransmitter(calls)}, _RecordingReceiver(calls), IrTransmitGate()
    )

    transceiver.update()

    assert calls == ["poll", "receive"]


def test_update_polls_every_wired_transmitter() -> None:
    calls: list = []
    transceiver = InfraredTransceiver(
        {LINE: _RecordingTransmitter(calls), CONE: _RecordingTransmitter(calls)},
        None,
        IrTransmitGate(),
    )

    transceiver.update()

    assert calls == ["poll", "poll"]


def test_update_with_no_receiver_still_polls_transmitters() -> None:
    calls: list = []
    transceiver = InfraredTransceiver({LINE: _RecordingTransmitter(calls)}, None, IrTransmitGate())

    transceiver.update()

    assert calls == ["poll"]


def test_update_with_no_transmitters_or_receiver_leaves_received_none() -> None:
    transceiver = InfraredTransceiver({}, None, IrTransmitGate())

    transceiver.update()  # must not raise

    assert transceiver.received is None


# ---------------------------------------------------------------------------
# received — set only on a decoding tick
# ---------------------------------------------------------------------------


def test_received_is_none_when_the_receiver_decodes_nothing() -> None:
    transceiver = InfraredTransceiver({}, _ScriptedReceiver([None]), IrTransmitGate())

    transceiver.update()

    assert transceiver.received is None


def test_received_holds_the_decoded_payload_on_a_decoding_tick() -> None:
    payload = bytearray(b"\xab\xcd")
    transceiver = InfraredTransceiver({}, _ScriptedReceiver([payload]), IrTransmitGate())

    transceiver.update()

    assert transceiver.received is payload


def test_received_resets_to_none_on_the_tick_after_a_decode() -> None:
    payload = bytearray(b"\x01")
    transceiver = InfraredTransceiver({}, _ScriptedReceiver([payload, None]), IrTransmitGate())

    transceiver.update()
    transceiver.update()

    assert transceiver.received is None


# ---------------------------------------------------------------------------
# apply_codec()
# ---------------------------------------------------------------------------


def test_apply_codec_fans_the_encoder_out_to_every_transmitter() -> None:
    calls: list = []
    encoder = AuraInfraredEncoder()
    transceiver = InfraredTransceiver(
        {
            LINE: _RecordingSetEncoderTransmitter(calls),
            CONE: _RecordingSetEncoderTransmitter(calls),
        },
        None,
        IrTransmitGate(),
    )

    transceiver.apply_codec(encoder, AuraInfraredDecoder())

    assert calls == [encoder, encoder]


def test_apply_codec_installs_the_decoder_on_the_receiver() -> None:
    receiver = _RecordingSetDecoderReceiver()
    decoder = AuraInfraredDecoder()
    transceiver = InfraredTransceiver({}, receiver, IrTransmitGate())

    transceiver.apply_codec(AuraInfraredEncoder(), decoder)

    assert receiver.decoder is decoder


def test_apply_codec_still_fans_out_the_encoder_with_no_receiver_wired() -> None:
    calls: list = []
    encoder = AuraInfraredEncoder()
    transceiver = InfraredTransceiver(
        {LINE: _RecordingSetEncoderTransmitter(calls)}, None, IrTransmitGate()
    )

    transceiver.apply_codec(encoder, AuraInfraredDecoder())  # must not raise

    assert calls == [encoder]


def test_apply_codec_still_installs_the_decoder_with_no_transmitters_wired() -> None:
    receiver = _RecordingSetDecoderReceiver()
    decoder = AuraInfraredDecoder()
    transceiver = InfraredTransceiver({}, receiver, IrTransmitGate())

    transceiver.apply_codec(AuraInfraredEncoder(), decoder)  # must not raise

    assert receiver.decoder is decoder


def test_apply_codec_is_a_safe_noop_with_no_transmitters_and_no_receiver() -> None:
    transceiver = InfraredTransceiver({}, None, IrTransmitGate())

    transceiver.apply_codec(AuraInfraredEncoder(), AuraInfraredDecoder())  # must not raise


# ---------------------------------------------------------------------------
# Forwarded telemetry attributes
# ---------------------------------------------------------------------------


def test_last_signal_strength_is_forwarded_from_the_receiver() -> None:
    payload = bytearray(b"\x42")
    reader = FakePulseReader(_encode_pulses(payload))
    receiver = InfraredSingleReceiver(reader, AuraInfraredDecoder())
    transceiver = InfraredTransceiver({}, receiver, IrTransmitGate())

    transceiver.update()

    assert transceiver.last_signal_strength == receiver.last_signal_strength == 1.0


def test_last_error_margin_is_forwarded_from_the_receiver() -> None:
    payload = bytearray(b"\x42")
    reader = FakePulseReader(_encode_pulses(payload))
    receiver = InfraredSingleReceiver(reader, AuraInfraredDecoder())
    transceiver = InfraredTransceiver({}, receiver, IrTransmitGate())

    transceiver.update()

    assert transceiver.last_error_margin == receiver.last_error_margin == 0


def test_telemetry_line_is_forwarded_from_the_receiver() -> None:
    payload = b"\x42"
    pulses = _encode_pulses(payload)
    reader = FakePulseReader(pulses)
    receiver = InfraredSingleReceiver(reader, AuraInfraredDecoder())
    transceiver = InfraredTransceiver({}, receiver, IrTransmitGate())

    transceiver.update()
    line = transceiver.telemetry_line()

    assert line == (
        "ir: pulses_seen=" + str(len(pulses)) + " buffer_full_on_poll=0 "
        "packets_started=0 preamble_reject=0 mark_reject=0 space_reject=0 "
        "packets_completed=0 packets_surfaced=1 pulses_dropped_transmitting=0"
    )


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
    receiver = InfraredSingleReceiver(reader, AuraInfraredDecoder(), gate)
    transceiver = InfraredTransceiver({LINE: tx}, receiver, gate)

    tx.send(b"\xaa")  # non-blocking writer stays busy — gate armed across ticks
    echo_pulses = _encode_pulses(b"\xaa")
    overlapping_shot_pulses = _encode_pulses(b"\xbb")
    reader.load(echo_pulses + overlapping_shot_pulses)

    transceiver.update()

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
    receiver = InfraredSingleReceiver(reader, AuraInfraredDecoder(), gate)
    transceiver = InfraredTransceiver({LINE: tx}, receiver, gate)

    tx.send(b"\xaa")  # gate armed
    reader.load(_encode_pulses(b"\xaa"))  # self-echo captured while transmitting
    transceiver.update()
    assert transceiver.received is None

    writer.set_busy(False)  # hardware signals the write completed
    reader.load([111])  # buffered echo tail still sitting in the reader
    transceiver.update()  # releases the gate; falling-edge flush drains the tail
    assert transceiver.received is None
    assert receiver.telemetry().pulses_dropped_transmitting > 0

    payload = b"\x07"
    reader.load(_encode_pulses(payload))
    transceiver.update()  # gate now fully idle — decodes normally

    assert transceiver.received == bytearray(payload)
