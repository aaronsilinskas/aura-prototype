"""InfraredTransceiver — board-free single owner of the IR hardware subsystem.

Builds and owns the transmitters, the receiver, and the shared IR transmit
gate that keeps a device from decoding its own self-echo, from the pulse
readers, emitter pins and writer factory the platform provides. Pumps its own
transmitters directly rather than through an ``engine``-side seam. Used by
the device and the Simulated device alike, and exposed as
``DeviceHardware.ir``.
"""

from engine.network import IR_EMITTERS
from hardware.shared.ir_codecs.aura import AuraInfraredDecoder, AuraInfraredEncoder
from hardware.shared.ir_codecs.base import InfraredDecoder, InfraredEncoder
from hardware.shared.ir_transport import (
    PulseReader,
    PulseWriter,
    _InfraredReceiver,
    _InfraredTransmitter,
    _IrTransmitGate,
)
from hardware.shared.polled_part import PolledPart

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Callable
    from typing import TypeVar

    # A pin is whatever the platform's writer factory takes (a board pin, a
    # pin reference), so it is passed through untouched.
    Pin = TypeVar("Pin")

__all__ = ["InfraredTransceiver"]


class InfraredTransceiver(PolledPart):
    """Owns and drives the whole IR subsystem for one device.

    Builds its own transmitters, receiver and shared IR transmit gate from
    what the platform provides. One gate is shared by the receiver and every
    transmitter, so a device never decodes its own self-echo. Everything
    speaks the Aura wire-frame until :meth:`apply_codec`.

    Reach a transmitter only through :meth:`send` and :meth:`busy`;
    :attr:`emitters` and :attr:`receives` say what is wired.

    Args:
        readers: One pulse reader per IR receiver; empty wires no receiver.
        emitter_pins: Emitter key (a member of ``IR_EMITTERS``) to whatever
            *writer_factory* needs to build that emitter's writer. An emitter
            absent from it is not wired, and :meth:`send` raises for it.
        writer_factory: Called with an emitter key and its pin, in
            ``IR_EMITTERS`` order; builds that emitter's writer and returns it
            paired with the writer kind.
    """

    __slots__ = ("_codec", "_receiver", "_transmitters", "_writer_kind", "received")

    def __init__(
        self,
        readers: "list[PulseReader]",
        emitter_pins: "dict[str, Pin]",
        writer_factory: "Callable[[str, Pin], tuple[PulseWriter, str]]",
    ) -> None:
        gate = _IrTransmitGate()
        self._receiver = _InfraredReceiver(readers, AuraInfraredDecoder, gate) if readers else None
        encoder = AuraInfraredEncoder()
        transmitters: dict[str, _InfraredTransmitter] = {}
        writer_kind: str | None = None
        for emitter in IR_EMITTERS:
            if emitter not in emitter_pins:
                continue
            writer, writer_kind = writer_factory(emitter, emitter_pins[emitter])
            transmitters[emitter] = _InfraredTransmitter(writer, encoder, gate)
        self._transmitters = transmitters
        self._writer_kind = writer_kind
        self._codec: tuple[type[InfraredEncoder], Callable[[], InfraredDecoder]] = (
            AuraInfraredEncoder,
            AuraInfraredDecoder,
        )
        self.received: bytearray | None = None

    @property
    def writer_kind(self) -> str | None:
        """The writer kind the writer factory last reported, for boot narration.

        ``None`` when no emitter is wired. Every emitter is on one board, so
        one kind describes them all.
        """
        return self._writer_kind

    @property
    def emitters(self) -> tuple[str, ...]:
        """The emitter constants a transmitter is wired to, in wiring order."""
        return tuple(self._transmitters)

    @property
    def receives(self) -> bool:
        """Whether a receiver is wired."""
        return self._receiver is not None

    def send(self, data: bytes, emitter: str) -> None:
        """Route *data* to the transmitter wired to *emitter*.

        Fire-and-forget: whether the write completes synchronously or is
        still in flight stays a transmitter-level detail.

        Args:
            data: Opaque payload bytes to transmit.
            emitter: One of the emitter constants (``LINE``, ``CONE``,
                ``AREA_OF_EFFECT``).

        Raises:
            ValueError: If *emitter* is not in the transmitter map.
        """
        tx = self._transmitters.get(emitter)
        if tx is None:
            raise ValueError(f"No transmitter wired for emitter: {emitter}")
        tx.send(data)

    def busy(self, emitter: str) -> bool:
        """Pump *emitter*'s transmitter and report whether it is still busy.

        Pumping is scoped to *emitter* alone; :meth:`update` remains the only
        way to pump every wired transmitter each tick.

        Args:
            emitter: One of the emitter constants (``LINE``, ``CONE``,
                ``AREA_OF_EFFECT``).

        Raises:
            ValueError: If *emitter* is not in the transmitter map.
        """
        tx = self._transmitters.get(emitter)
        if tx is None:
            raise ValueError(f"No transmitter wired for emitter: {emitter}")
        return tx.poll()

    def update(self, elapsed: float) -> None:
        """Pump every transmitter, then receive — in that order, every tick.

        Pumping runs unconditionally, even with no receiver wired: a
        deferred ``end_transmit`` from a non-blocking write can complete this
        same tick, and a later gate check must see it released promptly. Sets
        :attr:`received` to this tick's decoded packet, or ``None`` when
        nothing decoded or no receiver is wired — never left stale from a
        previous tick.
        """
        for tx in self._transmitters.values():
            tx.poll()

        receiver = self._receiver
        self.received = receiver.receive() if receiver is not None else None

    def apply_codec(
        self,
        encoder_class: type[InfraredEncoder],
        decoder_factory: "Callable[[], InfraredDecoder]",
    ) -> None:
        """Install the codec *encoder_class* and *decoder_factory* make up.

        Builds one encoder that every transmitter shares, and hands
        *decoder_factory* to the receiver, which builds a fresh decoder per
        reader. Both are called with no arguments.

        Applied uniformly, with no "differs from default?" branch — intended
        for a single call before the first tick, not guarded against mid-run
        use. A no-op for transmitters when none are wired, and the decoder
        step is skipped with no receiver.

        Args:
            encoder_class: The encoder class, as
                :func:`~hardware.shared.ir_codecs.codec_for` returns it.
            decoder_factory: Builds the matching decoder; usually the decoder
                class itself.
        """
        self._codec = (encoder_class, decoder_factory)

        encoder = encoder_class()
        for tx in self._transmitters.values():
            tx.set_encoder(encoder)

        receiver = self._receiver
        if receiver is not None:
            receiver.set_decoder(decoder_factory)

    @property
    def codec(self) -> "tuple[type[InfraredEncoder], Callable[[], InfraredDecoder]]":
        """The installed ``(encoder_class, decoder_factory)`` pair, as :meth:`apply_codec` took it.

        The Aura wire-frame pair until :meth:`apply_codec` is called.
        """
        return self._codec

    @property
    def last_signal_strength(self) -> float | None:
        """Normalised signal quality (0.0-1.0) forwarded from the receiver.

        ``None`` with no receiver wired, or before the receiver's first
        successful decode.
        """
        receiver = self._receiver
        return receiver.last_signal_strength if receiver is not None else None

    @property
    def last_error_margin(self) -> int | None:
        """Worst-case timing deviation (µs) forwarded from the receiver.

        ``None`` with no receiver wired, or before the receiver's first
        successful decode.
        """
        receiver = self._receiver
        return receiver.last_error_margin if receiver is not None else None

    @property
    def last_best_receiver(self) -> PulseReader | None:
        """The reader the receiver picked for the last packet, forwarded from it.

        ``None`` with no receiver wired, with a single reader, or before the
        receiver's first successful decode.
        """
        receiver = self._receiver
        return receiver.last_best_receiver if receiver is not None else None

    def telemetry_line(self) -> str | None:
        """Delegate to the receiver's change-gated telemetry summary.

        Returns ``None`` with no receiver wired, or when the receiver has
        nothing new to report.
        """
        receiver = self._receiver
        return receiver.telemetry_line() if receiver is not None else None
