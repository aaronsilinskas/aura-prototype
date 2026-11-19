"""RadioTransport, the half-duplex radio port.

One port serves both directions because a single RFM69-class chip is
half-duplex; there is no separate send/receive pair the way IR has
``PulseWriter``/``PulseReader``.
"""

__all__ = ["RadioTransport"]


class RadioTransport:
    """Port through which :class:`RadioTransceiver` reaches a half-duplex radio chip."""

    def send(self, data: bytes) -> None:
        """Transmit *data* as a radio packet.

        Fire-and-forget from the caller's perspective — implementations may
        block briefly (a few ms for a hardware send) but queue nothing.

        Args:
            data: Opaque payload bytes to transmit.
        """
        raise NotImplementedError

    def receive(self) -> "tuple[int, bytes] | None":
        """Return the next waiting packet as ``(from_byte, data)``, or ``None``.

        Non-blocking: the caller must be able to call this every tick without
        stalling. ``from_byte`` is the raw RadioHead "From" address (0-254);
        ``data`` is the opaque payload, untouched.

        Returns:
            ``(from_byte, data)`` when a packet is waiting, else ``None``.
        """
        raise NotImplementedError
