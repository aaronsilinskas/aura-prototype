"""CircuitPython pulseio adapters for the Aura IR transport layer.

Provides :class:`PulseInReader` and :class:`PulseOutWriter` — concrete
implementations of the hardware-agnostic :class:`~hardware.shared.ir_transport.PulseReader`
and :class:`~hardware.shared.ir_transport.PulseWriter` port abstractions — wired
to ``pulseio.PulseIn`` and ``pulseio.PulseOut`` respectively.

These are the hardware leaves; all protocol logic lives in
:mod:`hardware.shared.ir_protocol` and :mod:`hardware.shared.ir_transport`.

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

    __slots__ = ("_pulsein",)

    def __init__(self, pulsein: object) -> None:  # pulseio.PulseIn — no stub on CPython
        self._pulsein = pulsein

    def read_pulse(self) -> int | None:
        """Return the oldest available pulse duration in µs, or ``None``.

        Removes the returned pulse from the ``PulseIn`` buffer.  Non-blocking —
        returns ``None`` immediately when the buffer is empty.

        Returns:
            Pulse duration in µs, or ``None`` if no pulse is ready.
        """
        pulsein = self._pulsein
        if len(pulsein) == 0:
            return None
        pulse = pulsein[0]
        del pulsein[0]
        return pulse


class PulseOutWriter(PulseWriter):
    """Transmits IR pulses via a ``pulseio.PulseOut`` at 38 kHz carrier.

    Args:
        pulseout: A ``pulseio.PulseOut`` instance already configured for the
            transmit pin (frequency=38000, duty_cycle=0x8000 for 50 % carrier).
    """

    __slots__ = ("_pulseout",)

    def __init__(self, pulseout: object) -> None:  # pulseio.PulseOut — no stub on CPython
        self._pulseout = pulseout

    def write_pulses(self, durations: list[int]) -> None:
        """Send *durations* via the PulseOut hardware.

        Args:
            durations: Sequence of integer pulse durations (µs), alternating
                mark/space, starting with a mark.  The underlying
                ``pulseio.PulseOut.send`` call blocks until transmission
                completes.
        """
        self._pulseout.send(durations)
