"""Behaviour-driven tests for RadioManager (hardware/shared/radio_manager.py).

Covers:
- update() is a no-op when the transport is None; received stays None
- received is set only on a receiving tick, reset otherwise
- the built NetworkEvents.RadioReceived carries the stringified From byte as
  sender and the payload untouched as data
"""

from engine.network import NetworkEvents
from hardware.shared.radio_manager import RadioManager
from hardware.shared.radio_transport import RadioTransport

# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class _RecordingTransport(RadioTransport):
    """Recording fake — queue_receive loads pending (from_byte, data) pairs,
    replayed FIFO; receive_calls counts every receive() call for asserting
    polling discipline. send() is unused by RadioManager but recorded anyway,
    matching the port's full recording-fake contract (see
    test_radio_transport.py's RecordingRadioTransport)."""

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
    manager = RadioManager(None)

    manager.update()

    assert manager.received is None


# ---------------------------------------------------------------------------
# received — set only on a receiving tick
# ---------------------------------------------------------------------------


def test_received_is_none_when_the_transport_has_nothing_waiting():
    manager = RadioManager(_RecordingTransport())

    manager.update()

    assert manager.received is None


def test_received_holds_a_radio_received_event_on_a_receiving_tick():
    manager = RadioManager(_RecordingTransport([(3, b"\xab\xcd")]))

    manager.update()

    assert isinstance(manager.received, NetworkEvents.RadioReceived)


def test_received_resets_to_none_on_the_tick_after_a_receive():
    manager = RadioManager(_RecordingTransport([(3, b"\xab"), None]))

    manager.update()
    manager.update()

    assert manager.received is None


# ---------------------------------------------------------------------------
# RadioReceived field mapping
# ---------------------------------------------------------------------------


def test_received_sender_is_the_from_byte_stringified():
    manager = RadioManager(_RecordingTransport([(42, b"\xab")]))

    manager.update()

    assert manager.received.sender == "42"


def test_received_data_passes_through_untouched():
    payload = b"\xab\xcd\xef"
    manager = RadioManager(_RecordingTransport([(3, payload)]))

    manager.update()

    assert manager.received.data == payload


# ---------------------------------------------------------------------------
# Polling discipline
# ---------------------------------------------------------------------------


def test_update_polls_the_transport_receive_exactly_once_per_tick():
    transport = _RecordingTransport([None, None])
    manager = RadioManager(transport)

    manager.update()
    manager.update()

    assert transport.receive_calls == 2
