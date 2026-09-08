"""Behaviour-driven tests for UsbCdcTransport's line framing over a serial-like stream.

``UsbCdcTransport`` needs no ``usb_cdc`` import of its own -- it frames lines
over any object exposing ``read(n)``/``write(bytes)`` -- so these run under
plain CPython against a fake stream standing in for ``usb_cdc.data``, with no
CircuitPython stub required (unlike ``SdCardStorage``'s ``sdcardio``/``storage``).
"""

from hardware.circuitpython.usb_cdc_transport import UsbCdcTransport


class _FakeSerial:
    """Fake serial stream returning one scripted chunk per ``read()`` call."""

    def __init__(self, reads: "list[bytes]" = ()) -> None:
        self._reads = list(reads)
        self.written = b""

    def write(self, data: bytes) -> None:
        self.written += data

    def read(self, size: int) -> bytes:
        if self._reads:
            return self._reads.pop(0)
        return b""


def test_send_appends_a_newline_terminator_to_the_written_line():
    serial = _FakeSerial()
    transport = UsbCdcTransport(serial)

    transport.send(b"abc123")

    assert serial.written == b"abc123\n"


def test_recv_returns_one_line_without_its_newline_terminator():
    serial = _FakeSerial([b"abc123\n"])
    transport = UsbCdcTransport(serial)

    assert transport.recv() == b"abc123"


def test_recv_assembles_a_line_delivered_across_several_small_reads():
    serial = _FakeSerial([b"a", b"", b"bc\n"])
    transport = UsbCdcTransport(serial)

    assert transport.recv() == b"abc"


def test_recv_returns_each_line_in_order_when_two_arrive_in_one_read():
    serial = _FakeSerial([b"first\nsecond\n"])
    transport = UsbCdcTransport(serial)

    assert transport.recv() == b"first"
    assert transport.recv() == b"second"
