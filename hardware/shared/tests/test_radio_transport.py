"""Behaviour-driven tests for the RadioTransport port (hardware/shared/radio_transport.py).

Covers:
- RadioTransport base-class contract (send / receive raise NotImplementedError)
- RecordingRadioTransport: the recording fake this file's own tests drive to
  back both directions of the port
"""

import pytest

from hardware.shared.radio_transport import RadioTransport

# ---------------------------------------------------------------------------
# Port contract
# ---------------------------------------------------------------------------


def test_radio_transport_send_base_raises_not_implemented():
    transport = RadioTransport()

    with pytest.raises(NotImplementedError):
        transport.send(b"\xab")


def test_radio_transport_receive_base_raises_not_implemented():
    transport = RadioTransport()

    with pytest.raises(NotImplementedError):
        transport.receive()


# ---------------------------------------------------------------------------
# RecordingRadioTransport — the recording fake
# ---------------------------------------------------------------------------


class RecordingRadioTransport(RadioTransport):
    """Recording fake backing both directions of the half-duplex port.

    ``queue_receive`` feeds what a later ``receive`` returns; an empty queue
    yields ``None``, matching the port's non-blocking "nothing waiting"
    contract.
    """

    def __init__(self) -> None:
        self.sent: list[bytes] = []
        self._receive_queue: list[tuple[int, bytes]] = []

    def queue_receive(self, from_byte: int, data: bytes) -> None:
        self._receive_queue.append((from_byte, data))

    def send(self, data: bytes) -> None:
        self.sent.append(data)

    def receive(self) -> "tuple[int, bytes] | None":
        if self._receive_queue:
            return self._receive_queue.pop(0)
        return None


def test_recording_radio_transport_records_sent_payloads_in_order():
    transport = RecordingRadioTransport()

    transport.send(b"\x01")
    transport.send(b"\x02")

    assert transport.sent == [b"\x01", b"\x02"]


def test_recording_radio_transport_receive_returns_none_when_nothing_queued():
    transport = RecordingRadioTransport()

    assert transport.receive() is None


def test_recording_radio_transport_replays_queued_receives_fifo():
    transport = RecordingRadioTransport()
    transport.queue_receive(3, b"\xab")
    transport.queue_receive(7, b"\xcd")

    first = transport.receive()
    second = transport.receive()

    assert first == (3, b"\xab")
    assert second == (7, b"\xcd")
    assert transport.receive() is None
