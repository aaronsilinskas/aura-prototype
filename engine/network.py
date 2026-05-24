from engine.events import Event, EventGroup
from engine.state import NetworkControls

try:
    from typing import Final
except ImportError:
    pass

__all__ = ["HardwareNetworkControls", "NetworkEvents"]


class NetworkEvents:
    """Namespace for network-layer event types."""

    GROUP: "Final" = EventGroup("net")

    class IRReceived(Event):
        """Event fired when an IR packet is received."""

        __slots__ = ("data",)

        def __init__(self, data: bytes) -> None:
            super().__init__(NetworkEvents.GROUP, "ir_received")
            self.data = data

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


class HardwareNetworkControls(NetworkControls):
    """Concrete network controls for real hardware peripherals.

    Methods are no-ops until wired to actual hardware peripherals.
    """

    def send_ir(self, data: bytes) -> None:
        pass  # TODO: wire to hardware peripheral

    def send_radio(self, data: bytes) -> None:
        pass  # TODO: wire to hardware peripheral
