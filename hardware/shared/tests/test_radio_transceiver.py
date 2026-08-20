"""Behaviour-driven tests for RadioTransceiver (hardware/shared/radio_transceiver.py).

The _RecordingTransport fake is this suite's own board-free fixture, so these
tests run without radio hardware.
"""

import pytest

from hardware.shared.radio_transceiver import RadioTransceiver
from hardware.shared.radio_transport import RadioTransport

# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class _RecordingTransport(RadioTransport):
    """In-memory RadioTransport fake that records sends and replays queued receives FIFO."""

    def __init__(self, results: list | None = None) -> None:
        self._receive_queue = list(results) if results else []
        self.sent: list[bytes] = []
        self.receive_calls = 0

    def queue_receive(self, from_byte: int, data: bytes) -> None:
        self._receive_queue.append((from_byte, data))

    def send(self, data: bytes) -> None:
        self.sent.append(data)

    def receive(self) -> "tuple[int, bytes] | None":
        self.receive_calls += 1
        return self._receive_queue.pop(0) if self._receive_queue else None


# ---------------------------------------------------------------------------
# update() with no transport
# ---------------------------------------------------------------------------


def test_update_with_no_transport_is_a_noop():
    transceiver = RadioTransceiver(None)

    transceiver.update()  # must not raise

    assert transceiver.received is None
    assert transceiver.last_sender is None


# ---------------------------------------------------------------------------
# received / last_sender — set together only on a receiving tick
# ---------------------------------------------------------------------------


def test_received_and_last_sender_are_none_when_the_transport_has_nothing_waiting():
    transceiver = RadioTransceiver(_RecordingTransport())

    transceiver.update()

    assert transceiver.received is None
    assert transceiver.last_sender is None


def test_received_and_last_sender_are_set_together_on_a_receiving_tick():
    transceiver = RadioTransceiver(_RecordingTransport([(42, b"\xab\xcd")]))

    transceiver.update()

    assert transceiver.received == b"\xab\xcd"
    assert transceiver.last_sender == 42


def test_received_and_last_sender_reset_to_none_on_the_tick_after_a_receive():
    transceiver = RadioTransceiver(_RecordingTransport([(3, b"\xab"), None]))

    transceiver.update()
    transceiver.update()

    assert transceiver.received is None
    assert transceiver.last_sender is None


# ---------------------------------------------------------------------------
# Payload and From byte survive untouched
# ---------------------------------------------------------------------------


def test_received_payload_passes_through_untouched():
    payload = b"\xab\xcd\xef"
    transceiver = RadioTransceiver(_RecordingTransport([(3, payload)]))

    transceiver.update()

    assert transceiver.received == payload


def test_last_sender_holds_the_from_byte_at_its_upper_boundary():
    transceiver = RadioTransceiver(_RecordingTransport([(254, b"\x01")]))

    transceiver.update()

    assert transceiver.last_sender == 254


def test_last_sender_holds_the_from_byte_at_its_lower_boundary():
    transceiver = RadioTransceiver(_RecordingTransport([(0, b"\x01")]))

    transceiver.update()

    assert transceiver.last_sender == 0


# ---------------------------------------------------------------------------
# Polling discipline
# ---------------------------------------------------------------------------


def test_update_polls_the_transport_receive_exactly_once_per_tick():
    transport = _RecordingTransport([None, None])
    transceiver = RadioTransceiver(transport)

    transceiver.update()
    transceiver.update()

    assert transport.receive_calls == 2


# ---------------------------------------------------------------------------
# send() — fire-and-forget delegation, no emitter argument
# ---------------------------------------------------------------------------


def test_send_routes_the_payload_to_the_transport():
    transport = _RecordingTransport()
    transceiver = RadioTransceiver(transport)

    transceiver.send(b"\xab\xcd")

    assert transport.sent == [b"\xab\xcd"]


def test_send_is_a_noop_with_no_transport_wired():
    transceiver = RadioTransceiver(None)

    transceiver.send(b"\xab")  # must not raise


def test_send_takes_no_emitter_argument():
    transceiver = RadioTransceiver(_RecordingTransport())

    with pytest.raises(TypeError):
        transceiver.send(b"\xab", "line")


# ---------------------------------------------------------------------------
# No-event guarantee — this module builds no game event
# ---------------------------------------------------------------------------


def test_received_is_the_raw_payload_not_a_network_event():
    transceiver = RadioTransceiver(_RecordingTransport([(3, b"\xab")]))

    transceiver.update()

    assert type(transceiver.received) is bytes
