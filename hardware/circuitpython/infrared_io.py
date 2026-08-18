"""CircuitPython pulseio adapters for the Aura IR transport layer.

Provides :class:`PulseInReader` and :class:`PulseOutWriter` — concrete
implementations of the hardware-agnostic :class:`~hardware.shared.ir_transport.PulseReader`
and :class:`~hardware.shared.ir_transport.PulseWriter` port abstractions — wired
to ``pulseio.PulseIn`` and ``pulseio.PulseOut`` respectively.

These are the hardware leaves; all codec logic lives in
:mod:`hardware.shared.ir_codecs` and :mod:`hardware.shared.ir_transport`.

Usage::

    import pulseio
    from hardware.circuitpython.infrared_io import PulseInReader, PulseOutWriter

    pulsein = pulseio.PulseIn(rx_pin, maxlen=256, idle_state=True)
    reader = PulseInReader(pulsein)

    pulseout = pulseio.PulseOut(tx_pin, frequency=38000, duty_cycle=0x8000)
    writer = PulseOutWriter(pulseout)
"""

from hardware.shared.ir_transport import PulseReader, PulseWriter


class PulseInReader(PulseReader):
    """Reads IR pulses from a ``pulseio.PulseIn`` buffer one at a time.

    ``pulseio.PulseIn`` behaves like a circular FIFO: ``len(pulsein)`` returns
    the number of available durations, index 0 is the oldest, and
    ``del pulsein[0]`` removes it.

    Args:
        pulsein: A ``pulseio.PulseIn`` instance already configured for the
            receive pin (idle_state=True for active-low IR receivers).
    """

    __slots__ = ("_pulsein", "buffer_full_on_poll")

    def __init__(self, pulsein: object) -> None:  # pulseio.PulseIn — no stub on CPython
        self._pulsein = pulsein

        # Monotonic-since-boot count of reads that observed a full buffer —
        # a proxy for buffer-overrun pulse loss (pulseio exposes no real
        # overflow signal). Reset via reset_telemetry() on the receiver.
        self.buffer_full_on_poll: int = 0

    def read_pulse(self) -> int | None:
        """Return the oldest available pulse duration in µs, or ``None``.

        Removes the returned pulse from the ``PulseIn`` buffer.  Non-blocking —
        returns ``None`` immediately when the buffer is empty.  Increments
        ``buffer_full_on_poll`` when the buffer is found at ``maxlen`` —
        a proxy for pulses that may have been dropped by overrun.

        Returns:
            Pulse duration in µs, or ``None`` if no pulse is ready.
        """
        pulsein = self._pulsein
        count = len(pulsein)
        if count == 0:
            return None
        if count == pulsein.maxlen:
            self.buffer_full_on_poll += 1
        return pulsein.popleft()

    def reset_telemetry(self) -> None:
        """Zero ``buffer_full_on_poll`` (for CPython test resets)."""
        self.buffer_full_on_poll = 0


class PulseOutWriter(PulseWriter):
    """Transmits IR pulses via a ``pulseio.PulseOut`` at 38 kHz carrier.

    Args:
        pulseout: A ``pulseio.PulseOut`` instance already configured for the
            transmit pin (frequency=38000, duty_cycle=0x8000 for 50 % carrier).
    """

    __slots__ = ("_busy", "_pulseout")

    def __init__(self, pulseout: object) -> None:  # pulseio.PulseOut — no stub on CPython
        self._pulseout = pulseout
        self._busy: bool = False

    def write_pulses(self, durations: list[int]) -> None:
        """Send *durations* via the PulseOut hardware.

        Blocks until transmission completes. ``is_busy()`` reports ``True``
        for the duration of the call (set before ``send``, cleared after) —
        on a single-core runtime this window is never externally observable
        since the loop is frozen through the blocking call, but it keeps the
        contract honest for non-blocking writers.

        Args:
            durations: Sequence of integer pulse durations (µs), alternating
                mark/space, starting with a mark.
        """
        self._busy = True
        self._pulseout.send(durations)
        self._busy = False

    def is_busy(self) -> bool:
        """Return ``True`` while ``pulseout.send`` is in progress."""
        return self._busy
