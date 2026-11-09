"""HardwareNetworkControls — the concrete NetworkControls adapter."""

from __future__ import annotations

from engine.capabilities import MissingCapabilityError, ir_emitter_capability
from engine.network import IR_EMITTERS
from engine.state import NetworkControls
from hardware.shared.ir_transceiver import InfraredTransceiver
from hardware.shared.radio_transceiver import RadioTransceiver

__all__ = ["HardwareNetworkControls"]


class HardwareNetworkControls(NetworkControls):
    """Concrete, send-only network controls for real hardware peripherals.

    Implements ``NetworkControls`` only. The per-tick IR and radio receive
    lifecycles live on :meth:`InfraredTransceiver.update` and
    :meth:`RadioTransceiver.update`, reached by the runtime loop through
    ``DeviceHardware.ir`` and ``DeviceHardware.radio`` rather than this seam.

    A send on hardware the device lacks raises ``MissingCapabilityError``
    with ``scene`` set to ``None``: :meth:`send_ir` when IR or that emitter is
    absent, :meth:`send_radio` when the radio is.

    Args:
        ir: The wired :class:`InfraredTransceiver`, or ``None`` on a device
            with no ``ir`` section declared (or a disabled one).
        radio: The wired :class:`RadioTransceiver`, or ``None`` on a device
            with no radio peripheral declared.
    """

    __slots__ = ("_ir", "_radio")

    def __init__(
        self,
        ir: InfraredTransceiver | None,
        radio: RadioTransceiver | None = None,
    ) -> None:
        self._ir = ir
        self._radio = radio

    def send_ir(self, data: bytes, emitter: str) -> None:
        """Broadcast *data* via the wired :class:`InfraredTransceiver`.

        Fire-and-forget, delegating to :meth:`InfraredTransceiver.send`:
        whether the write completed synchronously or is still in flight is a
        transmitter-level detail, not something this seam surfaces.

        Args:
            data: Opaque payload bytes to transmit.
            emitter: One of the emitter constants: ``LINE``, ``CONE``, or
                ``AREA_OF_EFFECT``.

        Raises:
            ValueError: If *emitter* is not an emitter constant.
            MissingCapabilityError: If no transceiver is wired, or *emitter*
                has no transmitter wired on it.
        """
        if emitter not in IR_EMITTERS:
            raise ValueError(f"Unknown IR emitter: {emitter!r}")
        if self._ir is None or emitter not in self._ir.emitters:
            raise MissingCapabilityError(frozenset((ir_emitter_capability(emitter),)), None)
        self._ir.send(data, emitter)

    def send_radio(self, data: bytes) -> None:
        """Transmit *data* via the wired :class:`RadioTransceiver`.

        Fire-and-forget, matching ``send_ir``.

        Args:
            data: Opaque payload bytes to transmit.

        Raises:
            MissingCapabilityError: If no radio is wired.
        """
        if self._radio is None:
            raise MissingCapabilityError(frozenset(("radio",)), None)
        self._radio.send(data)
