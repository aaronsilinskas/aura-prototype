"""Port auto-detect: resolve the host serial port for a board's console or data channel.

Both channels look alike by device name, so the board toolkit tells them apart
by USB interface: ``repl_comports()`` for the console channel and
``data_comports()`` for the data channel (including a macOS composite-CDC
workaround).
"""

from collections.abc import Sequence
from enum import Enum

TYPE_CHECKING = False
if TYPE_CHECKING:
    from serial.tools.list_ports_common import ListPortInfo

__all__ = ["PortAutoDetectError", "SerialChannel", "find_port"]


class SerialChannel(Enum):
    """A board's USB-CDC serial channel; the value names it in error messages."""

    CONSOLE = "console"
    DATA = "data"


class PortAutoDetectError(Exception):
    """Zero or more than one port matched the channel and none was named explicitly."""


def select_single_port(comports: "Sequence[ListPortInfo]", channel: SerialChannel) -> str:
    """Pick the one port in *comports*, the ports already matched to *channel*.

    Zero or several (more than one board attached) is ambiguous and raises
    :class:`PortAutoDetectError` naming ``--port`` as the fix, rather than guessing.
    """
    if len(comports) == 1:
        return comports[0].device

    if not comports:
        raise PortAutoDetectError(
            f"no CircuitPython {channel.value} port found; connect the device or pass --port"
        )

    raise PortAutoDetectError(
        f"multiple CircuitPython {channel.value} ports found "
        f"({', '.join(c.device for c in comports)}); pass --port to select one"
    )


def find_port(channel: SerialChannel, *, explicit_port: "str | None" = None) -> str:
    """Resolve *channel*'s serial port: *explicit_port* if given, without scanning USB.

    Otherwise scans the board toolkit for *channel*'s ports and applies
    :func:`select_single_port`. The toolkit is imported here, not at module
    level, so pyserial stays out of module import.
    """
    if explicit_port is not None:
        return explicit_port

    from adafruit_board_toolkit import circuitpython_serial

    match channel:
        case SerialChannel.CONSOLE:
            comports = circuitpython_serial.repl_comports()
        case SerialChannel.DATA:
            comports = circuitpython_serial.data_comports()
    return select_single_port(comports, channel)
