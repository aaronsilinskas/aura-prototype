"""Host-side byte transport for the SD-sync data channel.

:class:`SerialTransport` frames protocol lines with the shared ``LineFramer``
from :mod:`hardware.shared.sd_sync_protocol`. It decodes nothing: SD-sync
frames are protocol bytes, not REPL text. :mod:`scripts.port_auto_detect`
finds the data-channel port it opens.
"""

from typing import Final

from hardware.shared.sd_sync_protocol import LineFramer, Transport, delimit_line
from scripts.deploy_watch import SerialHandle, open_serial_with_retry

__all__ = ["SerialTransport", "open_serial_transport"]

_DEFAULT_BAUD: Final = 115200


class SerialTransport(Transport):
    """Live SD-sync ``Transport`` framing protocol lines over a host serial port."""

    def __init__(self, handle: SerialHandle) -> None:
        self._handle = handle
        # Through the handle, not a bound ser.read: SerialHandle may swap .ser on reconnect.
        self._framer = LineFramer(lambda size: handle.ser.read(size))

    def send(self, line: bytes) -> None:
        """Write *line* followed by the delimiter :meth:`recv` looks for."""
        self._handle.ser.write(delimit_line(line))

    def recv(self) -> bytes:
        """Return the next line, with its delimiter stripped."""
        return self._framer.read_line()


def open_serial_transport(port: str, baud: int = _DEFAULT_BAUD) -> SerialTransport:
    """Open *port* (retrying transient failures) and wrap it as a :class:`SerialTransport`.

    Explicitly asserts DTR: ``usb_cdc.data`` only considers a host
    "connected" -- and delivers bytes written to it -- once DTR is
    asserted, and while most platforms' pyserial builds do this
    automatically on open, that isn't guaranteed everywhere.
    """
    ser = open_serial_with_retry(port, baud)
    ser.dtr = True
    return SerialTransport(SerialHandle(ser, port, baud))
