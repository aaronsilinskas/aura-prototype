"""Host-side wiring for the SD-sync data channel: port auto-detect and byte transport.

Enabling the on-device SD-sync app makes a CircuitPython board expose
*two* serial ports -- the console channel and the data channel that carries
the SD-sync protocol -- and their device names alone can't tell them apart.
:func:`find_data_port` asks
``adafruit_board_toolkit.circuitpython_serial.data_comports()``, which
distinguishes the two CDC interfaces (including a macOS composite-CDC
workaround).

:class:`SerialTransport` frames protocol lines with the shared ``LineFramer``
from :mod:`hardware.shared.sd_sync_protocol`. It decodes nothing: SD-sync
frames are protocol bytes, not REPL text.
"""

from collections.abc import Sequence
from typing import Final

from adafruit_board_toolkit import circuitpython_serial

from hardware.shared.sd_sync_protocol import LineFramer, Transport, delimit_line
from scripts.deploy_watch import SerialHandle, open_serial_with_retry

TYPE_CHECKING = False
if TYPE_CHECKING:
    from serial.tools.list_ports_common import ListPortInfo

__all__ = ["SdSyncPortError", "SerialTransport", "find_data_port", "open_serial_transport"]

_DEFAULT_BAUD: Final = 115200


class SdSyncPortError(Exception):
    """Zero or more than one data-channel port was found and none was named explicitly."""


def select_data_port(
    comports: "Sequence[ListPortInfo]", *, explicit_port: "str | None" = None
) -> str:
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
    """Resolve the data-channel serial port, auto-detecting via ``data_comports()``."""
    return select_data_port(circuitpython_serial.data_comports(), explicit_port=explicit_port)


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
