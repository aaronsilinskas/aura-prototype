"""Behaviour-driven tests for InfraredManager (hardware/shared/ir_manager.py).

Covers:
- update() pumps transmits before it receives (order asserted)
- received is set only on a decoding tick and reset otherwise
- last_signal_strength / last_error_margin / telemetry_line() forwarded from
  the receiver, and None-safe with no receiver wired
- the full self-echo suppression cycle driven through update(), using fake
  PulseReader/PulseWriter ports wired through the real IrTransmitGate,
  InfraredTransmitter, and InfraredSingleReceiver
"""

from engine.network import TransmitPump
from hardware.shared.ir_codecs.aura import AuraInfraredDecoder, AuraInfraredEncoder
from hardware.shared.ir_manager import InfraredManager
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


class _RecordingTransmitPump(TransmitPump):
    """Records each poll_transmits() call into a shared order list."""

    def __init__(self, calls: list) -> None:
        self._calls = calls

    def poll_transmits(self) -> dict:
        self._calls.append("pump")
        return {}


class _RecordingReceiver(InfraredReceiver):
    """Records each receive() call into a shared order list; returns nothing."""

    def __init__(self, calls: list) -> None:
        super().__init__()
        self._calls = calls

    def receive(self) -> bytearray | None:
        self._calls.append("receive")
        return None


class _StubTransmitPump(TransmitPump):
    """No-op pump — isolates receiver behaviour from a real transmitter."""

    def poll_transmits(self) -> dict:
        return {}


class _ScriptedReceiver(InfraredReceiver):
    """Returns a pre-scripted sequence of receive() results, one per call."""

    def __init__(self, results: list) -> None:
        super().__init__()
        self._results = list(results)

    def receive(self) -> bytearray | None:
        return self._results.pop(0) if self._results else None


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
# update() sequencing
# ---------------------------------------------------------------------------


def test_update_pumps_transmits_before_receiving():
    calls: list = []
    manager = InfraredManager(_RecordingTransmitPump(calls), _RecordingReceiver(calls))

    manager.update()

    assert calls == ["pump", "receive"]


def test_update_with_no_receiver_still_pumps():
    calls: list = []
    manager = InfraredManager(_RecordingTransmitPump(calls), None)

    manager.update()

    assert calls == ["pump"]


def test_update_with_no_receiver_leaves_received_none():
    manager = InfraredManager(_StubTransmitPump(), None)

    manager.update()

    assert manager.received is None


# ---------------------------------------------------------------------------
# received — set only on a decoding tick
# ---------------------------------------------------------------------------


def test_received_is_none_when_the_receiver_decodes_nothing():
    manager = InfraredManager(_StubTransmitPump(), _ScriptedReceiver([None]))

    manager.update()

    assert manager.received is None


def test_received_holds_the_decoded_payload_on_a_decoding_tick():
    payload = bytearray(b"\xab\xcd")
    manager = InfraredManager(_StubTransmitPump(), _ScriptedReceiver([payload]))

    manager.update()

    assert manager.received is payload


def test_received_resets_to_none_on_the_tick_after_a_decode():
    payload = bytearray(b"\x01")
    manager = InfraredManager(_StubTransmitPump(), _ScriptedReceiver([payload, None]))

    manager.update()
    manager.update()

    assert manager.received is None


# ---------------------------------------------------------------------------
# Forwarded telemetry attributes
# ---------------------------------------------------------------------------


def test_last_signal_strength_is_forwarded_from_the_receiver():
    payload = bytearray(b"\x42")
    reader = FakePulseReader(_encode_pulses(payload))
    receiver = InfraredSingleReceiver(reader, AuraInfraredDecoder())
    manager = InfraredManager(_StubTransmitPump(), receiver)

    manager.update()

    assert manager.last_signal_strength == receiver.last_signal_strength == 1.0


def test_last_error_margin_is_forwarded_from_the_receiver():
    payload = bytearray(b"\x42")
    reader = FakePulseReader(_encode_pulses(payload))
    receiver = InfraredSingleReceiver(reader, AuraInfraredDecoder())
    manager = InfraredManager(_StubTransmitPump(), receiver)

    manager.update()

    assert manager.last_error_margin == receiver.last_error_margin == 0


def test_telemetry_line_is_forwarded_from_the_receiver():
    payload = b"\x42"
    pulses = _encode_pulses(payload)
    reader = FakePulseReader(pulses)
    receiver = InfraredSingleReceiver(reader, AuraInfraredDecoder())
    manager = InfraredManager(_StubTransmitPump(), receiver)

    manager.update()
    line = manager.telemetry_line()

    assert line == (
        "ir: pulses_seen=" + str(len(pulses)) + " buffer_full_on_poll=0 "
        "packets_started=0 preamble_reject=0 mark_reject=0 space_reject=0 "
        "packets_completed=0 packets_surfaced=1 pulses_dropped_transmitting=0"
    )


def test_last_signal_strength_is_none_with_no_receiver_wired():
    manager = InfraredManager(_StubTransmitPump(), None)
    assert manager.last_signal_strength is None


def test_last_error_margin_is_none_with_no_receiver_wired():
    manager = InfraredManager(_StubTransmitPump(), None)
    assert manager.last_error_margin is None


def test_telemetry_line_is_none_with_no_receiver_wired():
    manager = InfraredManager(_StubTransmitPump(), None)
    assert manager.telemetry_line() is None


# ---------------------------------------------------------------------------
# Full self-echo suppression cycle, driven entirely through update()
# ---------------------------------------------------------------------------


class _SingleTransmitterPump(TransmitPump):
    """Minimal TransmitPump wrapping one InfraredTransmitter's poll()."""

    def __init__(self, transmitter: InfraredTransmitter) -> None:
        self._transmitter = transmitter

    def poll_transmits(self) -> dict:
        self._transmitter.poll()
        return {}


def test_update_discards_self_echo_and_an_overlapping_real_shot_while_transmitting():
    """A transmit arms the gate; while it stays armed, update() drains and
    discards both the self-echo and any real shot overlapping it — the two
    are indistinguishable at the pulse level, so both are dropped."""
    gate = IrTransmitGate()
    writer = ControllableFakePulseWriter()
    tx = InfraredTransmitter(writer, AuraInfraredEncoder(), gate)
    reader = FakePulseReader()
    receiver = InfraredSingleReceiver(reader, AuraInfraredDecoder(), gate)
    manager = InfraredManager(_SingleTransmitterPump(tx), receiver)

    tx.send(b"\xaa")  # non-blocking writer stays busy — gate armed across ticks
    echo_pulses = _encode_pulses(b"\xaa")
    overlapping_shot_pulses = _encode_pulses(b"\xbb")
    reader.load(echo_pulses + overlapping_shot_pulses)

    manager.update()

    assert manager.received is None
    assert receiver.telemetry().pulses_dropped_transmitting == (
        len(echo_pulses) + len(overlapping_shot_pulses)
    )


def test_update_falling_edge_flush_recovers_the_decoder_for_the_next_genuine_packet():
    """After the transmit ends, one more update() drain-discards the flush
    tail; the decoder returns to idle and the next real packet decodes
    normally — the inter-frame-gap recovery path."""
    gate = IrTransmitGate()
    writer = ControllableFakePulseWriter()
    tx = InfraredTransmitter(writer, AuraInfraredEncoder(), gate)
    reader = FakePulseReader()
    receiver = InfraredSingleReceiver(reader, AuraInfraredDecoder(), gate)
    manager = InfraredManager(_SingleTransmitterPump(tx), receiver)

    tx.send(b"\xaa")  # gate armed
    reader.load(_encode_pulses(b"\xaa"))  # self-echo captured while transmitting
    manager.update()
    assert manager.received is None

    writer.set_busy(False)  # hardware signals the write completed
    reader.load([111])  # buffered echo tail still sitting in the reader
    manager.update()  # releases the gate; falling-edge flush drains the tail
    assert manager.received is None
    assert receiver.telemetry().pulses_dropped_transmitting > 0

    payload = b"\x07"
    reader.load(_encode_pulses(payload))
    manager.update()  # gate now fully idle — decodes normally

    assert manager.received == bytearray(payload)
