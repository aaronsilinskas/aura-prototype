"""The exact SD-sync wire bytes, pinned for both live transports.

The host's ``SerialTransport`` and the device's ``UsbCdcTransport`` talk to
each other, so both must put the same bytes on the wire for the same frame.
The expected line is a literal, not recomputed from ``encode_frame``.
"""

from collections.abc import Sequence
from typing import TYPE_CHECKING, cast

import pytest

from hardware.circuitpython.usb_cdc_transport import UsbCdcTransport
from hardware.shared.sd_sync_protocol import Frame, Transport, decode_frame, encode_frame
from scripts.deploy_watch import SerialHandle
from scripts.sd_sync_transport import SerialTransport

if TYPE_CHECKING:
    import usb_cdc
    from serial import Serial

CHUNK_0_HI_ON_THE_WIRE = b"Y2h1bmsgMApoaQ==\n"


class _FakeStream:
    """Byte stream standing in for both a host serial port and ``usb_cdc.data``."""

    def __init__(self, reads: Sequence[bytes] = ()) -> None:
        self._reads = list(reads)
        self.written = b""
        self.timeout: float | None = None

    def write(self, data: bytes) -> None:
        self.written += data

    def read(self, size: int) -> bytes:
        if self._reads:
            return self._reads.pop(0)
        return b""


def _serial_transport(stream: _FakeStream) -> Transport:
    return SerialTransport(SerialHandle(cast("Serial", stream), "/dev/fake", 115200))


def _usb_cdc_transport(stream: _FakeStream) -> Transport:
    return UsbCdcTransport(cast("usb_cdc.Serial", stream))


TRANSPORTS = pytest.mark.parametrize(
    "make_transport",
    [_serial_transport, _usb_cdc_transport],
    ids=["host-serial", "device-usb-cdc"],
)


@TRANSPORTS
def test_sending_a_chunk_frame_writes_its_base64_line_then_one_newline(make_transport):
    stream = _FakeStream()

    make_transport(stream).send(encode_frame(Frame("chunk", "0", b"hi")))

    assert stream.written == CHUNK_0_HI_ON_THE_WIRE


@TRANSPORTS
def test_receiving_the_pinned_wire_bytes_yields_the_chunk_frame(make_transport):
    stream = _FakeStream([CHUNK_0_HI_ON_THE_WIRE])

    frame = decode_frame(make_transport(stream).recv())

    assert (frame.kind, frame.text, frame.payload) == ("chunk", "0", b"hi")
