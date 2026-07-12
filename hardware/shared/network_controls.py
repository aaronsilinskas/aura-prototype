"""HardwareNetworkControls — the concrete NetworkControls/TransmitPump adapter."""

from __future__ import annotations

from engine.network import TransmitPump
from engine.state import NetworkControls
from hardware.shared.ir_transport import InfraredTransmitter
from hardware.shared.radio_transport import RadioTransport

__all__ = ["HardwareNetworkControls"]


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
        radio: The wired :class:`RadioTransport`, or ``None`` on a device
            with no radio peripheral declared — in which case ``send_radio``
            is a no-op rather than raising, unlike ``send_ir``'s per-emitter
            map (radio has no name to look up; the whole capability is either
            present or absent).

    Radio never contributes to ``poll_transmits()`` — a single RFM69-class
    chip is half-duplex and ``send_radio`` is fire-and-forget, so there is no
    transmit lifecycle to pump.
    """

    __slots__ = ("_poll_results", "_radio", "_transmitters")

    def __init__(
        self,
        transmitters: dict[str, InfraredTransmitter],
        radio: RadioTransport | None = None,
    ) -> None:
        self._transmitters = transmitters
        self._radio = radio
        # Pre-allocated once, mutated in place by poll_transmits — a fresh
        # dict per call would be a hot-path allocation (poll_transmits runs
        # every tick in the real runtime loop).
        self._poll_results: dict[str, bool] = dict.fromkeys(transmitters, False)

    def send_ir(self, data: bytes, emitter: str) -> None:
        """Broadcast *data* via the :class:`InfraredTransmitter` for *emitter*.

        Fire-and-forget: whether the write completed synchronously or is
        still in flight is a transmitter-level detail (see
        :meth:`InfraredTransmitter.send`), not something this seam surfaces.

        Args:
            data: Opaque payload bytes to transmit.
            emitter: One of the emitter constants: ``LINE``, ``CONE``, or
                ``AREA_OF_EFFECT``.

        Raises:
            ValueError: If *emitter* is not in the transmitter map supplied at
                construction time.
        """
        tx = self._transmitters.get(emitter)
        if tx is None:
            raise ValueError("No transmitter wired for emitter: " + str(emitter))
        tx.send(data)

    def send_radio(self, data: bytes) -> None:
        """Transmit *data* via the wired :class:`RadioTransport`.

        Fire-and-forget, matching ``send_ir``. A no-op when no radio
        peripheral is wired (``radio=None`` at construction).

        Args:
            data: Opaque payload bytes to transmit.
        """
        if self._radio is not None:
            self._radio.send(data)

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
