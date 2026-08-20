"""RadioTransceiver — board-free single owner of a device's radio subsystem.

Mirrors :class:`~hardware.shared.ir_transceiver.InfraredTransceiver`'s
ownership shape: constructed with a transport seam that may be absent, its
``update`` polls that seam once per tick and exposes the result as attributes
read afterwards rather than returned. The port is private — no call site
reaches it through this class.

Assembled by ``device_builder._setup_radio`` and exposed as
``DeviceHardware.radio``; ``HardwareNetworkControls.send_radio`` delegates to
it. This class hands back the raw decoded payload and sender byte rather than
building a ``NetworkEvents.RadioReceived`` itself — it imports no
``engine.network`` vocabulary. The raw packet crosses into game vocabulary
only later, at ``run_scene``, which builds the event next to the IR block.
"""

from hardware.shared.radio_transport import RadioTransport

__all__ = ["RadioTransceiver"]


class RadioTransceiver:
    """Owns the per-tick radio receive poll and the fire-and-forget send.

    Constructed with the same ``radio`` transport seam intended for
    ``DeviceHardware`` — ``transport`` may be ``None`` on a device with no
    radio peripheral wired, in which case :meth:`update` and :meth:`send`
    are both no-ops.

    Args:
        transport: Polled every tick in :meth:`update` and written to by
            :meth:`send`, or ``None`` when no radio is wired.
    """

    __slots__ = ("_transport", "last_sender", "received")

    def __init__(self, transport: RadioTransport | None) -> None:
        self._transport = transport
        self.received: bytes | None = None
        self.last_sender: int | None = None

    def send(self, data: bytes) -> None:
        """Fire-and-forget *data* over the transport's single channel.

        Unlike :meth:`InfraredTransceiver.send`, there is no emitter to
        name — an RFM69-class radio chip has one channel, not a directed
        set of transmitters. Silent no-op when no transport is wired, the
        same way a device with no radio peripheral simply drops
        game-triggered sends rather than raising.

        Args:
            data: Opaque payload bytes to transmit.
        """
        if self._transport is not None:
            self._transport.send(data)

    def update(self) -> None:
        """Poll the transport once and refresh :attr:`received`/:attr:`last_sender`.

        Receive only. This does not pump or gate anything: the chip is
        half-duplex, and a fire-and-forget :meth:`send` leaves nothing to
        pump and produces no self-echo to gate against — unlike
        :meth:`InfraredTransceiver.update`, there is no transmit-pump step
        to run here, and none should be added later.

        Sets :attr:`received` and :attr:`last_sender` together to this
        tick's decoded payload and RadioHead "From" byte, or both to
        ``None`` when nothing decoded or no transport is wired — never left
        stale from a previous tick.
        """
        transport = self._transport
        packet = transport.receive() if transport is not None else None

        if packet is None:
            self.received = None
            self.last_sender = None
            return

        self.last_sender, self.received = packet
