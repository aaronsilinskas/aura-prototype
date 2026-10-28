"""The IR subsystem's one wiring, shared by the device builder and the Simulated device.

Board-free: the platform hands in the pulse readers it built and a factory for
each emitter's writer, so the gate, receiver and transmitters are put together
here and nowhere else.
"""

try:
    from collections.abc import Callable
except ImportError:
    pass

from engine.network import IR_EMITTERS
from hardware.shared.ir_codecs.aura import AuraInfraredDecoder, AuraInfraredEncoder
from hardware.shared.ir_transceiver import InfraredTransceiver
from hardware.shared.ir_transport import (
    InfraredReceiver,
    InfraredTransmitter,
    IrTransmitGate,
    PulseReader,
    PulseWriter,
)

__all__ = ["wire_ir"]


# A pin is whatever the platform's writer factory takes (a board pin, a config
# pin name), so it is passed through untouched and typed no tighter than object.
def wire_ir(
    readers: "list[PulseReader]",
    emitter_pins: "dict[str, object]",
    writer_factory: "Callable[[str, object], tuple[PulseWriter, str]]",
) -> "tuple[InfraredTransceiver, str | None]":
    """Wire the IR subsystem over *readers* and the emitters in *emitter_pins*.

    One :class:`IrTransmitGate` is shared by the receiver and every
    transmitter, so a device never decodes its own self-echo. Everything
    speaks the Aura wire-frame until
    :meth:`~hardware.shared.ir_transceiver.InfraredTransceiver.apply_codec`.

    Args:
        readers: One pulse reader per IR receiver; never empty.
        emitter_pins: Emitter key (a member of ``IR_EMITTERS``) to whatever
            the platform's *writer_factory* needs to build that emitter's
            writer. An emitter absent from it is not wired.
        writer_factory: Called with an emitter key and its pin, in
            ``IR_EMITTERS`` order; builds that emitter's writer and returns it
            paired with the writer kind.

    Returns:
        The transceiver, and the writer kind the factory last reported, or
        ``None`` when no emitter is wired. Every emitter is on one board, so
        one kind describes them all.
    """
    gate = IrTransmitGate()
    receiver = InfraredReceiver(readers, AuraInfraredDecoder, gate)
    encoder = AuraInfraredEncoder()
    transmitters: dict[str, InfraredTransmitter] = {}
    writer_kind: str | None = None
    for emitter in IR_EMITTERS:
        if emitter not in emitter_pins:
            continue
        writer, writer_kind = writer_factory(emitter, emitter_pins[emitter])
        transmitters[emitter] = InfraredTransmitter(writer, encoder, gate)
    return InfraredTransceiver(transmitters, receiver, gate), writer_kind
