"""UsbCdcTransport -- the live SD-sync ``Transport`` adapter over a USB-CDC data channel.

Frames :mod:`hardware.shared.sd_sync_protocol` lines with a trailing newline
delimiter -- ``encode_frame`` output is plain base64 and so never contains one
-- so a byte stream with no message boundaries of its own (like a serial port)
can still exchange one frame per :meth:`~UsbCdcTransport.send`/:meth:`~UsbCdcTransport.recv`.

Takes a ``usb_cdc.Serial`` -- on-device wiring passes ``usb_cdc.data``, the
channel ``hardware/circuitpython/boot.py`` opens -- but imports ``usb_cdc``
only for the checker. It touches just ``timeout``, ``read(size)`` and
``write(data)``, so tests pass a fake stream with those three.
"""

from __future__ import annotations

from hardware.shared.sd_sync_protocol import Transport

TYPE_CHECKING = False

if TYPE_CHECKING:
    import usb_cdc

__all__ = ["UsbCdcTransport"]

_READ_SIZE = 64


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
        self._buffered = b""

    def send(self, line: bytes) -> None:
        """Write *line* followed by the newline terminator :meth:`recv` looks for."""
        self._serial.write(line + b"\n")

    def recv(self) -> bytes:
        """Return the next newline-terminated line, with the terminator stripped.

        Reads in :data:`_READ_SIZE`-byte pieces, buffering across calls, until
        a newline appears; a stream that returns no bytes yet (a non-blocking
        ``read`` with nothing waiting) is retried in a tight loop -- acceptable
        for this single-connection device-side loop, which has nothing else to
        do while waiting for the next request.
        """
        while b"\n" not in self._buffered:
            chunk = self._serial.read(_READ_SIZE)
            if chunk:
                self._buffered += chunk
        line, _, self._buffered = self._buffered.partition(b"\n")
        return line
