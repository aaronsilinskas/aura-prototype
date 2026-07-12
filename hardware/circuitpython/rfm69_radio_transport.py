"""CircuitPython adapter wrapping adafruit_rfm69.RFM69 as the live RadioTransport.

The only module that imports ``adafruit_rfm69`` — ``hardware.shared.radio_transport``
and ``hardware.shared.radio_manager`` stay chip-agnostic, and ``device_builder``
reaches this module only through a deferred import inside its radio setup helper
(mirroring the audio/matrix/motor driver-library deferral pattern), so a config
with no ``radio`` section never requires ``adafruit_rfm69`` to be installed.
"""

import adafruit_rfm69

from hardware.shared.radio_transport import RadioTransport

__all__ = ["Rfm69RadioTransport"]


class Rfm69RadioTransport(RadioTransport):
    """Live ``RadioTransport`` backed by an ``adafruit_rfm69.RFM69`` chip.

    Constructs and owns the RFM69 driver instance itself from already-resolved
    hardware handles — an SPI bus and two ``digitalio.DigitalInOut`` pins — so
    ``device_builder`` never needs to import ``adafruit_rfm69`` to build a radio.

    Args:
        spi: The shared SPI bus (see ``device_builder._setup_spi``).
        cs: Chip-select pin, already wrapped as a ``digitalio.DigitalInOut``.
        reset: Reset pin, already wrapped as a ``digitalio.DigitalInOut``.
        frequency: Radio frequency in MHz (board-variant-specific).
        node: This device's id on the radio network, ``0``-``254``.
    """

    __slots__ = ("_radio",)

    def __init__(
        self,
        spi: object,
        cs: object,
        reset: object,
        frequency: float,
        node: int,
    ) -> None:
        radio = adafruit_rfm69.RFM69(spi, cs, reset, frequency)
        radio.node = node
        self._radio = radio

    def send(self, data: bytes) -> None:
        """Transmit *data*, then return the chip to RX (``keep_listening=True``)."""
        self._radio.send(data, keep_listening=True)

    def receive(self) -> "tuple[int, bytes] | None":
        """Return the next waiting packet as ``(from_byte, data)``, or ``None``.

        Non-blocking: gates on ``payload_ready`` so a tick with nothing
        waiting never stalls. Reads with ``with_header=True`` to recover the
        RadioHead From byte as *from_byte*; *data* is the payload with the
        4-byte header (to, from, id, flags) stripped.
        """
        radio = self._radio
        if not radio.payload_ready:
            return None
        packet = radio.receive(with_header=True)
        if packet is None:
            return None
        return packet[1], bytes(packet[4:])
