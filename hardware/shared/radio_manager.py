"""RadioManager — board-free per-tick owner of the radio receive path.

Mirrors :class:`~hardware.shared.ir_transceiver.InfraredTransceiver`'s
``update``/``received`` shape: a board-free orchestrator, constructed with a
seam that may be absent, whose :meth:`update` polls it once per tick and
exposes the result as an attribute read afterwards rather than returned.

Unlike IR, radio's receive orchestrator builds the game-facing event itself
rather than leaving that to ``run_scene``: the transport hands back a raw
``(from_byte, data)`` pair with no game vocabulary, and this is the one place
that pair becomes a ``NetworkEvents.RadioReceived``. It imports no other
game-vocabulary beyond that single event type.
"""

from engine.network import NetworkEvents
from hardware.shared.radio_transport import RadioTransport

__all__ = ["RadioManager"]


class RadioManager:
    """Owns the per-tick radio receive poll and the resulting event.

    Constructed with the same ``radio`` transport seam intended for
    ``DeviceHardware`` — ``transport`` may be ``None`` on a device with no
    radio peripheral wired, in which case :meth:`update` is a no-op.

    Radio has no transmit pump to run first (unlike IR): a single physical
    chip is half-duplex and ``send_radio`` is fire-and-forget, so
    :meth:`update` only polls receive.

    Args:
        transport: Polled every tick, or ``None`` when no radio is wired.
    """

    __slots__ = ("_transport", "received")

    def __init__(self, transport: RadioTransport | None) -> None:
        self._transport = transport
        self.received: NetworkEvents.RadioReceived | None = None

    def update(self) -> None:
        """Poll the transport once and rebuild :attr:`received` for this tick.

        Sets :attr:`received` to a freshly built ``NetworkEvents.RadioReceived``
        when a packet was waiting, or ``None`` when nothing was waiting (or no
        transport is wired) — never left stale from a previous tick. The
        event's ``sender`` is the transport's raw From byte, stringified;
        ``data`` passes through untouched.
        """
        transport = self._transport
        packet = transport.receive() if transport is not None else None

        if packet is None:
            self.received = None
            return

        from_byte, data = packet
        self.received = NetworkEvents.RadioReceived(data, str(from_byte))
