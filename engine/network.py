from engine.events import Event, EventGroup

try:
    from typing import Final
except ImportError:
    pass

__all__ = [
    "AREA_OF_EFFECT",
    "CONE",
    "IR_EMITTERS",
    "LINE",
    "NetworkEvents",
    "TransmitPump",
]

# ---------------------------------------------------------------------------
# IR emitter constants
# ---------------------------------------------------------------------------

LINE: Final = "line"
CONE: Final = "cone"
AREA_OF_EFFECT: Final = "area_of_effect"

# The single source of IR emitter identity: every module that needs the
# emitter key set (the parser's valid-key check, device_builder's wiring
# loop) derives it from this tuple instead of re-enumerating the constants.
IR_EMITTERS: Final = (LINE, CONE, AREA_OF_EFFECT)


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


class TransmitPump:
    """Runtime-facing seam for pumping in-flight transmit lifecycle work.

    A plain base class (not ``typing.Protocol``, which is unavailable on the
    constrained runtimes) — the same substitute pattern as ``VoiceSink``.
    Deliberately lives here rather than in ``engine/state.py``: that module
    stays purely rule-facing, and ``NetworkControls`` never gains this
    lifecycle method. The live adapter is ``HardwareNetworkControls``
    (``hardware/shared/network_controls.py``), reached by the runtime loop
    through ``DeviceHardware.transmit_pump`` rather than through the
    send-only ``NetworkControls`` handle.
    """

    __slots__ = ()

    def poll_transmits(self) -> dict[str, bool]:
        """Pump every wired transmitter's in-flight write lifecycle forward.

        Returns:
            A map of each wired emitter constant to that transmitter's busy
            state after this poll.
        """
        raise NotImplementedError
