"""HardwareNetworkControls — the concrete NetworkControls adapter."""

from __future__ import annotations

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

    Missing-transceiver behavior is asymmetric: :meth:`send_ir` raises
    because each call names an emitter that cannot be honored, while
    :meth:`send_radio` is a silent no-op — radio is present or absent as a
    whole, with no emitter name to fail on.

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
            ValueError: If no transceiver is wired, or *emitter* has no
                transmitter wired on the transceiver.
        """
        if self._ir is None:
            raise ValueError(f"No IR transceiver wired; cannot send on emitter: {emitter}")
        self._ir.send(data, emitter)

    def send_radio(self, data: bytes) -> None:
        """Transmit *data* via the wired :class:`RadioTransceiver`.

        Fire-and-forget, matching ``send_ir``. A silent no-op when no radio
        peripheral is wired (``radio=None`` at construction).

        Args:
            data: Opaque payload bytes to transmit.
        """
        if self._radio is not None:
            self._radio.send(data)
