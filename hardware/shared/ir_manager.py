"""InfraredManager — board-free per-tick owner of the IR pump-before-receive order.

Suppressing self-echo (a device decoding its own IR emission) depends on a
precise cross-object, cross-tick call order: ``poll_transmits()`` before
``receive()``. :class:`InfraredManager` makes that order code, driven by the
existing :class:`~engine.network.TransmitPump` and
:class:`~hardware.shared.ir_transport.InfraredReceiver` seams, rather than a
comment in the runtime loop. It does not reimplement the transmit gate.
"""

from engine.network import TransmitPump
from hardware.shared.ir_transport import InfraredReceiver

__all__ = ["InfraredManager"]


class InfraredManager:
    """Owns the per-tick IR sequence: pump transmits, then receive.

    Constructed with the same ``transmit_pump``/``ir_receiver`` seams already
    on ``DeviceHardware`` — ``ir_receiver`` may be ``None`` on a device with
    no receiver wired. :meth:`update` always pumps (a deferred
    ``end_transmit`` can be in flight across a scene transition) and receives
    only when a receiver is present.

    Results are read as attributes after :meth:`update`, matching the
    receiver's own ``last_*`` pattern, rather than returned: ``received``
    (this tick's packet or ``None``, reset every call), plus
    ``last_signal_strength``/``last_error_margin``/:meth:`telemetry_line`
    forwarded from the receiver (``None`` for all four with no receiver
    wired).

    Args:
        transmit_pump: Runtime-facing seam pumped every tick.
        ir_receiver: Receiver polled every tick, or ``None`` when no IR
            receiver is wired.
    """

    __slots__ = ("_ir_receiver", "_transmit_pump", "received")

    def __init__(
        self,
        transmit_pump: TransmitPump,
        ir_receiver: InfraredReceiver | None,
    ) -> None:
        self._transmit_pump = transmit_pump
        self._ir_receiver = ir_receiver
        self.received: bytearray | None = None

    def update(self) -> None:
        """Pump in-flight transmits, then receive if a receiver is wired.

        Pumping runs unconditionally, before the receive: a deferred
        ``end_transmit`` from a non-blocking write can complete this same
        tick, and the receiver's gate check must see it. Sets :attr:`received`
        to this tick's decoded packet, or ``None`` when nothing decoded (or
        no receiver is wired) — never left stale from a previous tick.
        """
        self._transmit_pump.poll_transmits()

        ir_receiver = self._ir_receiver
        self.received = ir_receiver.receive() if ir_receiver is not None else None

    @property
    def last_signal_strength(self) -> float | None:
        """Normalised signal quality (0.0-1.0) forwarded from the receiver.

        ``None`` with no receiver wired, or before the receiver's first
        successful decode.
        """
        ir_receiver = self._ir_receiver
        return ir_receiver.last_signal_strength if ir_receiver is not None else None

    @property
    def last_error_margin(self) -> int | None:
        """Worst-case timing deviation (µs) forwarded from the receiver.

        ``None`` with no receiver wired, or before the receiver's first
        successful decode.
        """
        ir_receiver = self._ir_receiver
        return ir_receiver.last_error_margin if ir_receiver is not None else None

    def telemetry_line(self) -> str | None:
        """Delegate to the receiver's change-gated telemetry summary.

        Returns ``None`` with no receiver wired, or when the receiver has
        nothing new to report (see
        :meth:`~hardware.shared.ir_transport.InfraredReceiver.telemetry_line`).
        """
        ir_receiver = self._ir_receiver
        return ir_receiver.telemetry_line() if ir_receiver is not None else None
