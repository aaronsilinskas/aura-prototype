from __future__ import annotations

from engine.events import Event, EventGroup

TYPE_CHECKING = False

if TYPE_CHECKING:
    from typing import Final

__all__ = [
    "AREA_OF_EFFECT",
    "CONE",
    "IR_EMITTERS",
    "LINE",
    "NetworkEvents",
]


LINE: Final = "line"
CONE: Final = "cone"
AREA_OF_EFFECT: Final = "area_of_effect"

# The single source of IR emitter identity: every module that needs the
# emitter key set derives it from this tuple instead of re-enumerating the constants.
IR_EMITTERS: Final = (LINE, CONE, AREA_OF_EFFECT)


class NetworkEvents:
    GROUP: Final = EventGroup("net")

    class IRReceived(Event):
        """Event fired when an IR packet is received.

        It names no receiver: an IR multi-receiver picks
        one for reliability only, never direction.
        """

        __slots__ = ("data", "error_margin", "signal_strength")

        def __init__(
            self,
            data: bytes | bytearray,
            signal_strength: float | None,
            error_margin: int | None,
        ) -> None:
            super().__init__(NetworkEvents.GROUP, "ir_received")
            self.data = data
            self.signal_strength = signal_strength
            self.error_margin = error_margin

    class RadioReceived(Event):
        """Event fired when a radio packet is received.

        ``sender`` is a free-form device identifier string provided by the
        hardware driver; the engine does not interpret its format.
        """

        __slots__ = ("data", "sender")

        def __init__(self, data: bytes, sender: str) -> None:
            super().__init__(NetworkEvents.GROUP, "radio_received")
            self.data = data
            self.sender = sender
