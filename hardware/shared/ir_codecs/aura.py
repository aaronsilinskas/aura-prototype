"""Aura IR wire-frame codec.

Concrete ``AuraInfraredEncoder`` / ``AuraInfraredDecoder`` implementations of
the shared base classes in :mod:`hardware.shared.ir_codecs.base`. The frame
carries a variable-length opaque payload plus a trailing CRC-8; the timing
constants below are the source of truth, and :class:`AuraInfraredEncoder`
documents the frame layout.

No ``pulseio`` import — safe on CPython, CircuitPython 10.x, and MicroPython.

The module-level ``ENCODER`` / ``DECODER`` names let a codec be resolved by
module (name → class pair), the convention shared across IR codec modules.
"""

from array import array

from hardware.shared.ir_codecs.base import InfraredDecoder, InfraredEncoder

try:
    from typing import Final
except ImportError:
    pass  # typing not available on all embedded runtimes

# ---------------------------------------------------------------------------
# Wire-frame timing constants (µs)
# ---------------------------------------------------------------------------

IR_UNIT: Final = 500

IR_HEADER_MARK: Final = IR_UNIT * 8  # 4000 µs
IR_HEADER_SPACE: Final = IR_UNIT * 6  # 3000 µs

IR_MARK_ZERO: Final = IR_UNIT  # 500 µs mark for a zero bit
IR_SPACE_ZERO: Final = IR_UNIT  # 500 µs space for a zero bit

IR_MARK_ONE: Final = IR_UNIT  # 500 µs mark for a one bit
IR_SPACE_ONE: Final = IR_UNIT * 3  # 1500 µs space for a one bit

IR_LEAD_OUT: Final = IR_UNIT * 10  # 5000 µs terminator

_IR_ERROR_MARGIN: Final = IR_UNIT // 2  # 250 µs — internal tolerance threshold
_CRC_GENERATOR: Final = 0x1D


# ---------------------------------------------------------------------------
# CRC-8 helper (no allocation — pure integer arithmetic)
# ---------------------------------------------------------------------------


def _calculate_crc(data: bytes | bytearray, length: int = -1) -> int:
    """Return the CRC-8 (generator ``0x1D``) of the first *length* bytes of *data*.

    A *length* of -1 (the default) covers the entire buffer.
    """
    if length == -1:
        length = len(data)
    crc = 0
    for i in range(length):
        crc ^= data[i]
        for _ in range(8):
            crc = ((crc << 1) & 0xFF) ^ (_CRC_GENERATOR if crc & 0x80 else 0)
    return crc


# ---------------------------------------------------------------------------
# Aura concrete encoder
# ---------------------------------------------------------------------------

# Decoder state constants
_STATE_IDLE: Final = 0
_STATE_HEADER_SPACE: Final = 1
_STATE_DATA: Final = 2


class AuraInfraredEncoder(InfraredEncoder):
    """Aura wire-frame IR encoder.

    Encodes an opaque payload as:
    ``[header_mark, header_space, <8 pairs per data byte>, <8 pairs for CRC>, lead_out]``

    Each bit is two entries: a mark (always ``IR_UNIT``) followed by a space
    (``IR_SPACE_ZERO`` for 0, ``IR_SPACE_ONE`` for 1).  MSB transmitted first.
    A CRC-8 byte (generator ``0x1D``) is appended before the lead-out.
    """

    def encode(self, data: bytes) -> array:
        """Encode *data* into an Aura IR pulse array.

        Args:
            data: Opaque payload (any length ≥ 1 byte).

        Returns:
            ``array.array('H', …)`` ready to pass to a pulse-output driver.
        """
        # Layout: 2 (header) + (len(data)+1)*8*2 (payload+CRC bits) + 1 (lead-out)
        n_bit_slots = (len(data) + 1) * 8 * 2  # mark+space pairs for payload and CRC
        n_slots = 2 + n_bit_slots + 1
        pulses = array("H", bytearray(n_slots * 2))  # zero-init via bytearray — no temp list

        pulses[0] = IR_HEADER_MARK
        pulses[1] = IR_HEADER_SPACE

        idx = 2
        for byte in data:
            idx = self._encode_byte(pulses, idx, byte)

        crc = _calculate_crc(data)
        self._encode_byte(pulses, idx, crc)

        pulses[-1] = IR_LEAD_OUT
        return pulses

    @staticmethod
    def _encode_byte(pulses: array, idx: int, value: int) -> int:
        """Write 8-bit *value* MSB-first into *pulses* starting at *idx*.

        Returns the next free index after writing 16 entries (8 mark+space pairs).
        """
        for _ in range(8):
            if value & 0x80:
                pulses[idx] = IR_MARK_ONE
                pulses[idx + 1] = IR_SPACE_ONE
            else:
                pulses[idx] = IR_MARK_ZERO
                pulses[idx + 1] = IR_SPACE_ZERO
            value = (value << 1) & 0xFF
            idx += 2
        return idx


# ---------------------------------------------------------------------------
# Aura concrete decoder
# ---------------------------------------------------------------------------


class AuraInfraredDecoder(InfraredDecoder):
    """Aura wire-frame IR decoder.

    Stateful pulse-by-pulse decoder.  Feed each received pulse duration (µs)
    to :meth:`decode`; it returns a ``bytearray`` payload when a complete,
    CRC-verified packet has been received, or ``None`` otherwise.

    The decoder silently discards unrecognised pulses while idle (searching
    for the header mark) and resets on any protocol violation during reception.
    """

    __slots__ = ("_awaiting_space",)

    def __init__(self) -> None:
        super().__init__(_IR_ERROR_MARGIN)
        # True while waiting for the space half of the current bit
        self._awaiting_space: bool = False

    def decode(self, pulse: int) -> bytearray | None:
        """Process one pulse and return payload bytes when a packet completes.

        Args:
            pulse: Pulse duration in microseconds.

        Returns:
            ``bytearray`` payload on successful decode; ``None`` otherwise.
        """
        if self._decoder_state == _STATE_IDLE:
            if self._check_pulse(pulse, IR_HEADER_MARK):
                self._decoder_state = _STATE_HEADER_SPACE

        elif self._decoder_state == _STATE_HEADER_SPACE:
            if self._check_pulse(pulse, IR_HEADER_SPACE):
                self._decoder_state = _STATE_DATA
                self._awaiting_space = False
            else:
                self.reset(self._error_threshold)

        elif self._decoder_state == _STATE_DATA:
            if not self._awaiting_space:
                # Both zero and one bits share the same mark duration (IR_UNIT).
                if self._check_pulse(pulse, IR_MARK_ZERO):
                    self._awaiting_space = True
                elif self._check_pulse(pulse, IR_LEAD_OUT):
                    return self._finalise()
                else:
                    self.reset(self._error_threshold)
            else:
                # Space encodes the bit value. The two space durations are
                # >=1000 µs apart, well outside the 250 µs error window, so
                # either check order classifies unambiguously.
                if self._check_pulse(pulse, IR_SPACE_ONE):
                    self._write_bit(1)
                    self._awaiting_space = False
                elif self._check_pulse(pulse, IR_SPACE_ZERO):
                    self._write_bit(0)
                    self._awaiting_space = False
                else:
                    self.reset(self._error_threshold)

        return None

    def _finalise(self) -> bytearray | None:
        """Validate CRC and return payload, or reset and return ``None``."""
        data = self._received_data
        n = len(data)
        if n < 2:
            # Need at least 1 payload byte + 1 CRC byte
            self.reset(self._error_threshold)
            return None

        payload_len = n - 1
        received_crc = data[payload_len]
        calculated_crc = _calculate_crc(data, payload_len)

        saved_margin = self._max_error_margin
        if received_crc == calculated_crc:
            payload = data[:payload_len]  # bytearray slice returns bytearray — no extra wrap
            self.reset(saved_margin)
            return payload

        # CRC mismatch — reject silently
        self.reset(self._error_threshold)
        return None


# ---------------------------------------------------------------------------
# Resolution convention: module-level ENCODER / DECODER
# ---------------------------------------------------------------------------

ENCODER = AuraInfraredEncoder
DECODER = AuraInfraredDecoder
