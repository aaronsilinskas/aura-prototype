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
    "TransmitPump",
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


class TransmitPump:
    """Runtime-facing seam for pumping in-flight transmit lifecycle work.

    A plain base class (not ``typing.Protocol``, which is unavailable on the
    constrained runtimes) — the same substitute pattern as ``VoiceSink``.
    Deliberately lives here rather than in ``engine/state.py``: that module
    stays purely rule-facing, and ``NetworkControls`` never gains this
    lifecycle method. The live adapter is ``HardwareNetworkControls``, reached
    by the runtime loop through ``DeviceHardware.transmit_pump`` rather than
    through the send-only ``NetworkControls`` handle.
    """

    __slots__ = ()

    def poll_transmits(self) -> dict[str, bool]:
        """Pump every wired transmitter's in-flight write lifecycle forward."""
        raise NotImplementedError


class HardwareNetworkControls(NetworkControls, TransmitPump):
    """Concrete network controls for real hardware peripherals.

    Two-faced by design, mirroring ``AudioEffectOutput(EffectOutput,
    VoiceSink)``: a send-command surface through ``NetworkControls`` (what
    rules see via ``GameState.network_controls``) and a runtime-facing
    transmit-lifecycle pump through ``TransmitPump`` (what the runtime loop
    reaches via ``DeviceHardware.transmit_pump``) — the same object, two
    declared types, no downcast needed at either call site.

    Args:
        transmitters: Map from emitter constant (``LINE``, ``CONE``,
            ``AREA_OF_EFFECT``) to the :class:`InfraredTransmitter` wired to
            that physical emitter.  Pass an empty dict when no IR emitters are
            connected; ``send_ir`` will raise ``ValueError`` for any emitter.

    ``send_radio`` remains a no-op until a radio peripheral is wired.
    """

    __slots__ = ("_poll_results", "_transmitters")

    def __init__(self, transmitters: dict[str, InfraredTransmitter]) -> None:
        self._transmitters = transmitters
        # Pre-allocated once, mutated in place by poll_transmits — a fresh
        # dict per call would be a hot-path allocation (poll_transmits runs
        # every tick in the real runtime loop).
        self._poll_results: dict[str, bool] = dict.fromkeys(transmitters, False)

    def send_ir(self, data: bytes, emitter: str) -> bool:
        """Transmit *data* via the :class:`InfraredTransmitter` for *emitter*.

        Args:
            data: Opaque payload bytes to transmit.
            emitter: One of the emitter constants: ``LINE``, ``CONE``, or
                ``AREA_OF_EFFECT``.

        Returns:
            ``True`` only if *data* was fully transmitted synchronously
            (a blocking writer completed within this call); ``False`` if it
            was buffered because the transmitter was busy, or if the write
            started but is still in flight on a non-blocking/DMA writer.

        Raises:
            ValueError: If *emitter* is not in the transmitter map supplied at
                construction time.
        """
        tx = self._transmitters.get(emitter)
        if tx is None:
            raise ValueError("No transmitter wired for emitter: " + str(emitter))
        return tx.send(data)

    def send_radio(self, data: bytes) -> None:
        pass  # TODO: wire to hardware peripheral

    def poll_transmits(self) -> dict[str, bool]:
        """Pump every wired :class:`InfraredTransmitter`'s ``poll()``.

        Runtime-facing — must be called every tick so a non-blocking write
        in flight on any emitter eventually fires its deferred
        ``end_transmit`` and starts its pending send. Declared by
        ``TransmitPump``, not the abstract ``NetworkControls``: it is a
        lifecycle/runtime concern, not a game rule, so it stays off the seam
        game rules see.

        Returns:
            The same ``dict[str, bool]`` instance every call (pre-allocated
            at construction, updated in place) mapping each wired emitter
            constant to that transmitter's busy state after this poll. A
            live view, not a snapshot — read it within the same tick.
        """
        results = self._poll_results
        for emitter, tx in self._transmitters.items():
            results[emitter] = tx.poll()
        return results
