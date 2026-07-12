"""RadioTransport — the board-free half-duplex radio port.

Provides the ``RadioTransport`` port abstraction that ``RadioManager`` and
``HardwareNetworkControls.send_radio`` reach the physical radio peripheral
through. One port serves both directions because a single RFM69-class chip
is half-duplex — there is no separate send/receive pair the way IR has
``PulseWriter``/``PulseReader``.

No ``adafruit_rfm69`` import — safe on CPython, CircuitPython 10.x, and
MicroPython. The live CircuitPython adapter wrapping ``adafruit_rfm69.RFM69``
is a separate, device-only module.
"""

__all__ = ["RadioTransport"]


class RadioTransport:
    """Port through which ``RadioManager`` and ``HardwareNetworkControls``
    reach a half-duplex radio chip.

    A plain base class — the same substitute pattern as ``VoiceSink`` and
    ``PulseReader``/``PulseWriter`` (``typing.Protocol`` is unavailable on
    the constrained runtimes). Subclass and override both methods to connect
    to hardware (e.g. ``adafruit_rfm69.RFM69``) or a test fake.
    """

    def send(self, data: bytes) -> None:
        """Transmit *data* as a radio packet.

        Fire-and-forget from the caller's perspective — implementations may
        block briefly (a few ms for a hardware send) but queue nothing.

        Args:
            data: Opaque payload bytes to transmit.

        Raises:
            NotImplementedError: Always — subclasses must override.
        """
        raise NotImplementedError

    def receive(self) -> "tuple[int, bytes] | None":
        """Return the next waiting packet as ``(from_byte, data)``, or ``None``.

        Non-blocking: the caller must be able to call this every tick without
        stalling. ``from_byte`` is the raw RadioHead "From" address (0-254);
        ``data`` is the opaque payload, untouched.

        Returns:
            ``(from_byte, data)`` when a packet is waiting, else ``None``.

        Raises:
            NotImplementedError: Always — subclasses must override.
        """
        raise NotImplementedError
