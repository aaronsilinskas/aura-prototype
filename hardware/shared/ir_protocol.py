"""Hardware-agnostic IR protocol codec for the Aura platform.

Provides base classes ``InfraredEncoder`` and ``InfraredDecoder``, and the
concrete Aura wire-frame implementation (``AuraInfraredEncoder`` /
``AuraInfraredDecoder``).

No ``pulseio`` import — safe on CPython, CircuitPython 10.x, and MicroPython.

Wire-frame constants (all times in microseconds):

- ``IR_UNIT`` = 500 µs — base timing unit
- Header mark = 4000 µs (8 × unit), header space = 3000 µs (6 × unit)
- Bit mark = 500 µs (1 × unit) for both 0 and 1
- Bit space zero = 500 µs (1 × unit), bit space one = 1500 µs (3 × unit)
- Lead-out terminator = 5000 µs (10 × unit)
- CRC-8 with generator 0x1D, MSB-first, variable-length opaque payload
"""

from array import array

try:
    from typing import Final
except ImportError:
    pass  # typing not available on all embedded runtimes

# ---------------------------------------------------------------------------
# Wire-frame timing constants (µs)
# ---------------------------------------------------------------------------

IR_UNIT: "Final" = 500

IR_HEADER_MARK: "Final" = IR_UNIT * 8  # 4000 µs
IR_HEADER_SPACE: "Final" = IR_UNIT * 6  # 3000 µs

IR_MARK_ZERO: "Final" = IR_UNIT  # 500 µs mark for a zero bit
IR_SPACE_ZERO: "Final" = IR_UNIT  # 500 µs space for a zero bit

IR_MARK_ONE: "Final" = IR_UNIT  # 500 µs mark for a one bit
IR_SPACE_ONE: "Final" = IR_UNIT * 3  # 1500 µs space for a one bit

IR_LEAD_OUT: "Final" = IR_UNIT * 10  # 5000 µs terminator

_IR_ERROR_MARGIN: "Final" = IR_UNIT // 2  # 250 µs — internal tolerance threshold
_CRC_GENERATOR: "Final" = 0x1D


# ---------------------------------------------------------------------------
# CRC-8 helper (no allocation — pure integer arithmetic)
# ---------------------------------------------------------------------------


def _calculate_crc(data: "bytes | bytearray", length: int = -1) -> int:
    """Return the CRC-8 (generator 0x1D) of the first *length* bytes of *data*.

    Accepts ``bytes`` or ``bytearray``.  If *length* is -1 (default) the
    entire buffer is used.
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
# Abstract base classes
# ---------------------------------------------------------------------------


class InfraredEncoder:
    """Abstract base: encodes byte payloads into IR pulse sequences.

    Subclasses implement :meth:`encode` to map opaque bytes onto an
    ``array.array`` of pulse durations (µs), alternating mark/space.
    No ``pulseio`` dependency — the array is passed to the hardware layer
    by the caller.
    """

    def encode(self, data: bytes) -> array:
        """Encode *data* into a pulse-duration array.

        Args:
            data: Opaque payload bytes to transmit.

        Returns:
            ``array.array('H', …)`` of pulse durations in microseconds,
            alternating mark/space, starting with a mark.

        Raises:
            NotImplementedError: Always — subclasses must override.
        """
        raise NotImplementedError


class InfraredDecoder:
    """Abstract base: stateful IR pulse-stream decoder.

    Processes one pulse at a time via :meth:`decode`, tracks the worst-case
    timing *error margin* across the current packet, and exposes a normalised
    *signal strength* (0.0–1.0) after each successful decode.

    Args:
        error_threshold: Maximum tolerated timing deviation in µs.  Pulses
            that deviate more than this from their expected value are rejected.

    Attributes:
        last_error_margin: Worst-case timing deviation (µs) for the last
            decoded packet, or ``None`` before any packet is decoded.
        last_signal_strength: Normalised quality metric (0.0–1.0) derived
            from *last_error_margin*.  An error ≤ 30 % of the threshold
            counts as full strength (1.0).  ``None`` before first decode.
    """

    def __init__(self, error_threshold: int) -> None:
        self._error_threshold = error_threshold

        # State machine position
        self._decoder_state: int = 0
        # Byte accumulator — cleared in place on reset to avoid per-packet allocation
        self._received_data: bytearray = bytearray()
        # Bit-writer state (MSB-first: starts at bit 7)
        self._received_bit_index: int = 7
        self._received_byte: int = 0

        # Timing-error tracking for the current packet
        self._max_error_margin: int = 0
        # Timing-error result from the last completed packet (None = never decoded)
        self._last_error_margin: int | None = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def decode(self, pulse: int) -> "bytearray | None":
        """Process a single pulse duration and return decoded data if complete.

        Args:
            pulse: Pulse duration in microseconds.

        Returns:
            ``bytearray`` payload if a complete, valid packet was decoded;
            ``None`` if more pulses are needed, an error occurred, or the
            packet was rejected.

        Raises:
            NotImplementedError: Always — subclasses must override.
        """
        raise NotImplementedError

    @property
    def last_error_margin(self) -> "int | None":
        """Worst-case timing deviation (µs) from the last decoded packet.

        Returns ``None`` before any packet has been successfully decoded.
        """
        return self._last_error_margin

    @property
    def last_signal_strength(self) -> "float | None":
        """Normalised signal quality (0.0–1.0) from the last decoded packet.

        An error margin of 0 or ≤ 30 % of the error threshold yields 1.0.
        Returns ``None`` before any packet has been decoded.
        """
        if self._last_error_margin is None:
            return None
        if self._last_error_margin == 0:
            return 1.0
        error_ratio = self._last_error_margin / self._error_threshold
        return min(1.0, 1.3 - error_ratio)

    # ------------------------------------------------------------------
    # Helpers for subclasses (not part of the public API)
    # ------------------------------------------------------------------

    def _reset(self, error_margin: "int | None") -> None:
        """Reset decoder state and record *error_margin* for this packet."""
        self._decoder_state = 0
        self._received_data.clear()  # mutate in place — no allocation
        self._received_bit_index = 7
        self._received_byte = 0
        self._max_error_margin = 0
        self._last_error_margin = error_margin

    def _check_pulse(self, received: int, expected: int) -> bool:
        """Return ``True`` if *received* is within the error threshold of *expected*.

        Tracks the worst-case deviation in ``_max_error_margin``.
        """
        margin = abs(received - expected)
        if margin < self._error_threshold:
            if margin > self._max_error_margin:
                self._max_error_margin = margin
            return True
        return False

    def _write_bit(self, bit: int) -> None:
        """Accumulate *bit* (0 or 1) MSB-first into the current byte."""
        if bit:
            self._received_byte |= 1 << self._received_bit_index
        self._received_bit_index -= 1
        if self._received_bit_index < 0:
            self._received_data.append(self._received_byte)
            self._received_byte = 0
            self._received_bit_index = 7


# ---------------------------------------------------------------------------
# Aura concrete encoder
# ---------------------------------------------------------------------------

# Decoder state constants
_STATE_IDLE: "Final" = 0
_STATE_HEADER_SPACE: "Final" = 1
_STATE_DATA: "Final" = 2


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
        pulses = array("H", [0] * (2 + n_bit_slots + 1))

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

    def __init__(self) -> None:
        super().__init__(_IR_ERROR_MARGIN)
        # True while waiting for the space half of the current bit
        self._awaiting_space: bool = False

    def decode(self, pulse: int) -> "bytearray | None":
        """Process one pulse and return payload bytes when a packet completes.

        States:
        - ``_STATE_IDLE``: scan for header mark; discard non-matching pulses.
        - ``_STATE_HEADER_SPACE``: expect header space; reset on mismatch.
        - ``_STATE_DATA``: alternate between bit marks, bit spaces, and lead-out.

        IR_SPACE_ONE is checked before IR_SPACE_ZERO in the space branch.
        Both are at least 1000 µs apart so they cannot fall within each
        other's error window (threshold = 250 µs).

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
                self._reset(self._error_threshold)

        elif self._decoder_state == _STATE_DATA:
            if not self._awaiting_space:
                # Both zero and one bits share the same mark duration (IR_UNIT).
                if self._check_pulse(pulse, IR_MARK_ZERO):
                    self._awaiting_space = True
                elif self._check_pulse(pulse, IR_LEAD_OUT):
                    return self._finalise()
                else:
                    self._reset(self._error_threshold)
            else:
                # Space determines bit value. Check one first — further from zero.
                if self._check_pulse(pulse, IR_SPACE_ONE):
                    self._write_bit(1)
                    self._awaiting_space = False
                elif self._check_pulse(pulse, IR_SPACE_ZERO):
                    self._write_bit(0)
                    self._awaiting_space = False
                else:
                    self._reset(self._error_threshold)

        return None

    def _finalise(self) -> "bytearray | None":
        """Validate CRC and return payload, or reset and return ``None``."""
        data = self._received_data
        n = len(data)
        if n < 2:
            # Need at least 1 payload byte + 1 CRC byte
            self._reset(self._error_threshold)
            return None

        payload_len = n - 1
        received_crc = data[payload_len]
        calculated_crc = _calculate_crc(data, payload_len)

        saved_margin = self._max_error_margin
        if received_crc == calculated_crc:
            payload = bytearray(data[:payload_len])
            self._reset(saved_margin)
            return payload

        # CRC mismatch — reject silently
        self._reset(self._error_threshold)
        return None
