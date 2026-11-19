"""UsbCdcTransport -- the live SD-sync ``Transport`` adapter over a USB-CDC data channel.

Frames lines with :mod:`hardware.shared.sd_sync_protocol`'s ``LineFramer``, so
a byte stream with no message boundaries of its own can still exchange one
frame per :meth:`~UsbCdcTransport.send`/:meth:`~UsbCdcTransport.recv`.
"""

from __future__ import annotations

from hardware.shared.sd_sync_protocol import LineFramer, Transport, frame_line

TYPE_CHECKING = False

if TYPE_CHECKING:
    import usb_cdc

__all__ = ["UsbCdcTransport"]


class UsbCdcTransport(Transport):
    """Live ``Transport`` framing SD-sync lines over a serial-like stream.

    Args:
        serial: The stream to frame lines over -- on-device, ``usb_cdc.data``.
    """

    def __init__(self, serial: usb_cdc.Serial) -> None:
        # usb_cdc.Serial defaults to a None (infinite) timeout, which makes
        # read(size) block until exactly size bytes arrive -- recv() below
        # relies on a non-blocking read (whatever's available now, even
        # nothing) so it can poll for a newline across short frames instead.
        serial.timeout = 0
        self._serial = serial
        self._framer = LineFramer()

    def send(self, line: bytes) -> None:
        """Write *line* followed by the delimiter :meth:`recv` looks for."""
        self._serial.write(frame_line(line))

    def recv(self) -> bytes:
        """Return the next line, with its delimiter stripped.

        Polling a non-blocking read in a tight loop is acceptable for this
        single-connection device-side loop, which has nothing else to do while
        waiting for the next request.
        """
        return self._framer.read_line(self._serial.read)
