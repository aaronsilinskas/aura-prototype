"""Behaviour-driven tests for Rfm69RadioTransport (hardware/circuitpython/rfm69_radio_transport.py).

Covers:
- send() transmits via the underlying RFM69 with keep_listening=True, so the
  chip returns to RX after transmitting
- receive() gates on payload_ready, never blocking when nothing is waiting
- receive() reads with_header=True and recovers the RadioHead From byte as
  sender, payload as data

``adafruit_rfm69`` is stubbed into ``sys.modules`` by the sibling conftest.py
so this suite runs under CPython; the RFM69 class itself is a MagicMock
substituted per test via ``patch``.
"""

from unittest.mock import MagicMock, patch

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_transport(mock_radio: MagicMock):
    """Return an Rfm69RadioTransport whose underlying RFM69 is *mock_radio*."""
    with patch("hardware.circuitpython.rfm69_radio_transport.adafruit_rfm69.RFM69") as mock_cls:
        mock_cls.return_value = mock_radio

        from hardware.circuitpython.rfm69_radio_transport import Rfm69RadioTransport

        return Rfm69RadioTransport(
            spi=MagicMock(name="spi"),
            cs=MagicMock(name="cs"),
            reset=MagicMock(name="reset"),
            frequency=915.0,
            node=1,
        )


# ---------------------------------------------------------------------------
# construction — configures the driver for non-blocking reads
# ---------------------------------------------------------------------------


def test_construction_disables_receive_timeout_so_driver_reads_never_block() -> None:
    mock_radio = MagicMock(name="radio")

    _build_transport(mock_radio)

    assert mock_radio.receive_timeout is None


# ---------------------------------------------------------------------------
# send() — transmits with keep_listening=True
# ---------------------------------------------------------------------------


def test_send_transmits_payload_with_keep_listening_so_chip_returns_to_rx() -> None:
    mock_radio = MagicMock(name="radio")
    transport = _build_transport(mock_radio)

    transport.send(b"\xab\xcd")

    mock_radio.send.assert_called_once_with(b"\xab\xcd", keep_listening=True)


# ---------------------------------------------------------------------------
# receive() — non-blocking, gated on payload_ready
# ---------------------------------------------------------------------------


def test_receive_returns_none_without_calling_receive_when_nothing_is_waiting() -> None:
    mock_radio = MagicMock(name="radio")
    mock_radio.payload_ready = False
    transport = _build_transport(mock_radio)

    result = transport.receive()

    assert result is None
    mock_radio.receive.assert_not_called()


def test_receive_recovers_from_byte_as_sender_and_strips_the_header() -> None:
    mock_radio = MagicMock(name="radio")
    mock_radio.payload_ready = True
    # RadioHead header: [to, from, id, flags] followed by the payload.
    mock_radio.receive.return_value = bytes([0x02, 0x07, 0x00, 0x00]) + b"\xab\xcd"
    transport = _build_transport(mock_radio)

    result = transport.receive()

    assert result == (7, b"\xab\xcd")


def test_receive_reads_with_header_true() -> None:
    mock_radio = MagicMock(name="radio")
    mock_radio.payload_ready = True
    mock_radio.receive.return_value = bytes([0x02, 0x07, 0x00, 0x00]) + b"\xab"
    transport = _build_transport(mock_radio)

    transport.receive()

    assert mock_radio.receive.call_args.kwargs.get("with_header") is True


def test_receive_returns_none_when_payload_ready_but_receive_yields_nothing() -> None:
    """payload_ready can flip false between the check and the read on a real
    chip (interrupt-driven) -- receive() honors a None from the underlying
    driver rather than crashing on it."""
    mock_radio = MagicMock(name="radio")
    mock_radio.payload_ready = True
    mock_radio.receive.return_value = None
    transport = _build_transport(mock_radio)

    result = transport.receive()

    assert result is None
