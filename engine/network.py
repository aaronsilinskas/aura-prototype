from engine.events import Event, EventGroup
from engine.state import NetworkControls
from hardware.shared.ir_transport import InfraredTransmitter

try:
    from typing import Final
except ImportError:
    pass

__all__ = [
    "AREA_OF_EFFECT",
    "CONE",
    "LINE",
    "HardwareNetworkControls",
    "NetworkEvents",
]

# ---------------------------------------------------------------------------
# IR emitter constants
# ---------------------------------------------------------------------------

LINE: Final = "line"
CONE: Final = "cone"
AREA_OF_EFFECT: Final = "area_of_effect"


class NetworkEvents:
    """Namespace for network-layer event types."""

    GROUP: Final = EventGroup("net")

    class IRReceived(Event):
        """Event fired when an IR packet is received.

        Carries full telemetry: raw payload, normalised signal quality,
        worst-case timing deviation, and the best-matching receiver name.
        """

        __slots__ = ("best_receiver", "data", "error_margin", "signal_strength")

        def __init__(
            self,
            data: bytes,
            signal_strength: float | None,
            error_margin: int | None,
            best_receiver: str | None,
        ) -> None:
            super().__init__(NetworkEvents.GROUP, "ir_received")
            self.data = data
            self.signal_strength = signal_strength
            self.error_margin = error_margin
            self.best_receiver = best_receiver

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

    Args:
        transmitters: Map from emitter constant (``LINE``, ``CONE``,
            ``AREA_OF_EFFECT``) to the :class:`InfraredTransmitter` wired to
            that physical emitter.  Pass an empty dict when no IR emitters are
            connected; ``send_ir`` will raise ``ValueError`` for any emitter.

    ``send_radio`` remains a no-op until a radio peripheral is wired.
    """

    def __init__(self, transmitters: dict[str, InfraredTransmitter]) -> None:
        self._transmitters = transmitters

    def send_ir(self, data: bytes, emitter: str) -> None:
        """Transmit *data* via the :class:`InfraredTransmitter` for *emitter*.

        Args:
            data: Opaque payload bytes to transmit.
            emitter: One of the emitter constants: ``LINE``, ``CONE``, or
                ``AREA_OF_EFFECT``.

        Raises:
            ValueError: If *emitter* is not in the transmitter map supplied at
                construction time.
        """
        tx = self._transmitters.get(emitter)
        if tx is None:
            raise ValueError("No transmitter wired for emitter: " + str(emitter))
        tx.send(data)

    def send_radio(self, data: bytes) -> None:
        pass  # TODO: wire to hardware peripheral
