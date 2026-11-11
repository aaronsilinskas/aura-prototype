"""Behaviour-driven tests for UsbCdcTransport's line framing over a serial-like stream.

``UsbCdcTransport`` imports ``usb_cdc`` only for the checker and touches just
``timeout``, ``read(n)`` and ``write(bytes)`` on its stream, so these run under
plain CPython against a fake stream standing in for ``usb_cdc.data``, with no
CircuitPython stub required (unlike ``SdCardStorage``'s ``sdcardio``/``storage``).
"""

from collections.abc import Sequence
from typing import TYPE_CHECKING, cast

from hardware.circuitpython.usb_cdc_transport import UsbCdcTransport

if TYPE_CHECKING:
    import usb_cdc


class _FakeSerial:
    """Fake serial stream returning one scripted chunk per ``read()`` call."""

    def __init__(self, reads: Sequence[bytes] = ()) -> None:
        self._reads = list(reads)
        self.written = b""

    def write(self, data: bytes) -> None:
        self.written += data

    def read(self, size: int) -> bytes:
        if self._reads:
            return self._reads.pop(0)
        return b""


def as_serial(serial: _FakeSerial) -> "usb_cdc.Serial":
    return cast("usb_cdc.Serial", serial)


def test_send_appends_a_newline_terminator_to_the_written_line():
    serial = _FakeSerial()
    transport = UsbCdcTransport(as_serial(serial))

    transport.send(b"abc123")

    assert serial.written == b"abc123\n"


def test_recv_returns_one_line_without_its_newline_terminator():
    serial = _FakeSerial([b"abc123\n"])
    transport = UsbCdcTransport(as_serial(serial))

    assert transport.recv() == b"abc123"


def test_recv_assembles_a_line_delivered_across_several_small_reads():
    serial = _FakeSerial([b"a", b"", b"bc\n"])
    transport = UsbCdcTransport(as_serial(serial))

    assert transport.recv() == b"abc"


def test_recv_returns_each_line_in_order_when_two_arrive_in_one_read():
    serial = _FakeSerial([b"first\nsecond\n"])
    transport = UsbCdcTransport(as_serial(serial))

    assert transport.recv() == b"first"
    assert transport.recv() == b"second"
