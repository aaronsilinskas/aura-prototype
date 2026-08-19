"""InfraredTransceiver — board-free single owner of the IR hardware subsystem.

Owns the transmitter map, the receiver, and the shared :class:`IrTransmitGate`
that keeps a device from decoding its own self-echo. Imports only the IR
primitives from :mod:`hardware.shared.ir_transport` and the codec base types
from :mod:`hardware.shared.ir_codecs.base` — no ``engine`` import, since this
class pumps its own transmitters directly rather than reaching them through
an ``engine``-side pump seam.

Assembled by :func:`~hardware.circuitpython.device_builder._setup_ir` and
wired into :func:`~hardware.circuitpython.device_builder.build_hardware` as
``DeviceHardware.ir`` and the ``ir`` reference
``HardwareNetworkControls.send_ir`` delegates to — the single owner that
replaced the old split across ``HardwareNetworkControls``'s transmitter map,
``DeviceHardware.ir_receiver``, and ``InfraredManager``.
"""

from hardware.shared.ir_codecs.base import InfraredDecoder, InfraredEncoder
from hardware.shared.ir_transport import InfraredReceiver, InfraredTransmitter, IrTransmitGate

__all__ = ["InfraredTransceiver"]


class InfraredTransceiver:
    """Owns and drives the whole IR subsystem for one device.

    Constructed with the same ``{emitter: InfraredTransmitter}`` map,
    ``InfraredReceiver | None``, and shared :class:`IrTransmitGate` that
    :func:`~hardware.circuitpython.device_builder._setup_ir` already builds
    today. The gate is stored only as the assembly owner — it is already
    wired into every transmitter and the receiver at construction time, so
    this class never calls it directly.

    The transmitter map is never exposed as a raw collection; reach a
    transmitter only through :meth:`send`.

    Args:
        transmitters: Map from emitter constant (``LINE``, ``CONE``,
            ``AREA_OF_EFFECT``) to the :class:`InfraredTransmitter` wired to
            that physical emitter. An empty dict means no emitters are
            wired; :meth:`send` then raises ``ValueError`` for every emitter.
        receiver: The wired :class:`InfraredReceiver`, or ``None`` on a
            device with no IR receiver.
        gate: The :class:`IrTransmitGate` shared by *transmitters* and
            *receiver* — owned here as the assembly reference, not driven.
    """

    __slots__ = ("_gate", "_receiver", "_transmitters", "received")

    def __init__(
        self,
        transmitters: dict[str, InfraredTransmitter],
        receiver: InfraredReceiver | None,
        gate: IrTransmitGate,
    ) -> None:
        self._transmitters = transmitters
        self._receiver = receiver
        self._gate = gate
        self.received: bytearray | None = None

    def send(self, data: bytes, emitter: str) -> None:
        """Route *data* to the transmitter wired to *emitter*.

        Fire-and-forget, mirroring :meth:`InfraredTransmitter.send` — whether
        the write completes synchronously or is still in flight stays a
        transmitter-level detail.

        Args:
            data: Opaque payload bytes to transmit.
            emitter: One of the emitter constants (``LINE``, ``CONE``,
                ``AREA_OF_EFFECT``).

        Raises:
            ValueError: If *emitter* is not in the transmitter map supplied
                at construction time.
        """
        tx = self._transmitters.get(emitter)
        if tx is None:
            raise ValueError(f"No transmitter wired for emitter: {emitter}")
        tx.send(data)

    def update(self) -> None:
        """Pump every transmitter, then receive — in that order, every tick.

        Pumping runs unconditionally, even with no receiver wired: a
        deferred ``end_transmit`` from a non-blocking write can complete
        this same tick, and a receiver's gate check must see it released
        promptly. Sets :attr:`received` to this tick's decoded packet, or
        ``None`` when nothing decoded or no receiver is wired — never left
        stale from a previous tick.
        """
        for tx in self._transmitters.values():
            tx.poll()

        receiver = self._receiver
        self.received = receiver.receive() if receiver is not None else None

    def apply_codec(self, encoder: InfraredEncoder, decoder: InfraredDecoder) -> None:
        """Install *encoder* on every transmitter and *decoder* on the receiver.

        Fans *encoder* out to every wired transmitter via
        :meth:`InfraredTransmitter.set_encoder` — a no-op when no
        transmitters are wired. Installs *decoder* on the receiver via
        :meth:`InfraredReceiver.set_decoder` when a receiver is wired; the
        decoder step is skipped entirely with no receiver. Applied
        uniformly, with no "differs from default?" branch — intended for a
        single call before the first tick, not guarded against mid-run use.

        Args:
            encoder: The encoder instance to install on every transmitter.
            decoder: The decoder instance to install on the receiver.
        """
        for tx in self._transmitters.values():
            tx.set_encoder(encoder)

        receiver = self._receiver
        if receiver is not None:
            receiver.set_decoder(decoder)

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

    def telemetry_line(self) -> str | None:
        """Delegate to the receiver's change-gated telemetry summary.

        Returns ``None`` with no receiver wired, or when the receiver has
        nothing new to report (see
        :meth:`~hardware.shared.ir_transport.InfraredReceiver.telemetry_line`).
        """
        receiver = self._receiver
        return receiver.telemetry_line() if receiver is not None else None
