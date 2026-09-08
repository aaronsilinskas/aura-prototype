"""Host-side wiring for the SD-sync data channel: port auto-detect and byte transport.

Enabling the on-device SD-sync app (#930) makes a CircuitPython board expose
*two* ``/dev/tty.usbmodem*`` ports -- one for the REPL, one for the data
channel that carries the SD-sync protocol -- so ``deploy_watch``'s
"exactly one match" glob (:func:`scripts.deploy_watch.find_port`) can no
longer tell them apart. :func:`find_data_port` instead asks
``adafruit_board_toolkit.circuitpython_serial.data_comports()``, which
already knows how to distinguish the two CDC interfaces (and carries the
macOS composite-CDC workaround `deploy_watch` doesn't need).

:class:`SerialTransport` is the live SD-sync ``Transport`` adapter for that
port: it reuses ``deploy_watch``'s ``SerialHandle``/``_open_serial_with_retry``
to open the connection, then frames protocol lines the same way
:class:`~hardware.circuitpython.usb_cdc_transport.UsbCdcTransport` does on the
device side -- a trailing newline delimiter, since ``encode_frame``'s base64
output never contains one. Unlike ``deploy_watch``'s own
:func:`~scripts.deploy_watch.iter_serial_lines`, there is no UTF-8 decoding
here: SD-sync frames are protocol bytes, not REPL text.
"""

from typing import Final

from adafruit_board_toolkit import circuitpython_serial

from hardware.shared.sd_sync_protocol import Transport
from scripts.deploy_watch import SerialHandle, _open_serial_with_retry

__all__ = ["SdSyncPortError", "SerialTransport", "find_data_port", "open_serial_transport"]

_DEFAULT_BAUD: Final = 115200
_READ_SIZE: Final = 64


class SdSyncPortError(Exception):
    """Zero or more than one data-channel port was found and none was named explicitly."""


def select_data_port(comports: "list[object]", *, explicit_port: "str | None" = None) -> str:
    """Pick the data-channel port from *comports* (each exposing a ``.device`` path).

    *explicit_port* always wins when given, bypassing auto-detect entirely.
    Otherwise exactly one comport must be present -- zero or several is
    ambiguous and raises :class:`SdSyncPortError` naming ``--port`` as the
    fix, rather than guessing.
    """
    if explicit_port is not None:
        return explicit_port

    if len(comports) == 1:
        return comports[0].device

    raise SdSyncPortError(
        f"found {len(comports)} CircuitPython data ports "
        f"(expected exactly 1: {[c.device for c in comports]}); pass --port to select one"
    )


def find_data_port(*, explicit_port: "str | None" = None) -> str:
    """Resolve the data-channel serial port, auto-detecting via ``data_comports()``.

    See :func:`select_data_port` for the selection rule; this wraps it with
    the live comport scan (not itself unit-tested -- it is a thin call into
    ``adafruit_board_toolkit``).
    """
    return select_data_port(circuitpython_serial.data_comports(), explicit_port=explicit_port)


class SerialTransport(Transport):
    """Live SD-sync ``Transport`` framing protocol lines over a host serial port.

    Args:
        handle: The open connection, from ``deploy_watch``'s
            ``SerialHandle``/``_open_serial_with_retry`` (see
            :func:`open_serial_transport`).
    """

    def __init__(self, handle: SerialHandle) -> None:
        self._handle = handle
        self._buffered = b""

    def send(self, line: bytes) -> None:
        """Write *line* followed by the newline terminator :meth:`recv` looks for."""
        self._handle.ser.write(line + b"\n")

    def recv(self) -> bytes:
        """Return the next newline-terminated line, with the terminator stripped.

        Reads in ``_READ_SIZE``-byte pieces, buffering across calls, until a
        newline appears -- mirrors ``UsbCdcTransport.recv``'s framing so both
        ends of the SD-sync link agree on message boundaries.
        """
        while b"\n" not in self._buffered:
            chunk = self._handle.ser.read(_READ_SIZE)
            if chunk:
                self._buffered += chunk
        line, _, self._buffered = self._buffered.partition(b"\n")
        return line


def open_serial_transport(port: str, baud: int = _DEFAULT_BAUD) -> SerialTransport:
    """Open *port* (retrying transient failures) and wrap it as a :class:`SerialTransport`."""
    ser = _open_serial_with_retry(port, baud)
    return SerialTransport(SerialHandle(ser, port, baud))
