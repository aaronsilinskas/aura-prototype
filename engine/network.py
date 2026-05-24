from engine.events import Event, EventGroup

try:
    from typing import Final
except ImportError:
    pass


class NetworkEvents:
    """Namespace for network-layer event types."""

    GROUP: "Final" = EventGroup("net")

    class IRReceived(Event):
        """Event fired when an IR packet is received.

        Attributes:
            data: Raw bytes of the received IR packet.
        """

        __slots__ = ("data",)

        def __init__(self, data: bytes) -> None:
            super().__init__(NetworkEvents.GROUP, "ir_received")
            self.data = data

    class RadioReceived(Event):
        """Event fired when a radio packet is received.

        Attributes:
            data: Raw bytes of the received radio packet.
            sender: Device identifier string for the transmitting device.
        """

        __slots__ = ("data", "sender")

        def __init__(self, data: bytes, sender: str) -> None:
            super().__init__(NetworkEvents.GROUP, "radio_received")
            self.data = data
            self.sender = sender
