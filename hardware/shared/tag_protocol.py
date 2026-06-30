"""Infrared tag IR protocol codec for the Aura platform.

Provides ``TagData`` (the data layer) plus ``encode_tag_data`` /
``decode_tag_data``, and the wire layer ``TagInfraredEncoder`` /
``TagInfraredDecoder`` which subclass :class:`InfraredEncoder` /
:class:`InfraredDecoder` from ``hardware.shared.ir_protocol``.

This is a port of the external infrared tag protocol so Aura devices can send
and receive shots that interoperate with third-party tag hardware. The wire
timings and bit alignment are an immutable compatibility contract — they are
preserved verbatim from the upstream reference implementation
(https://github.com/aaronsilinskas/infrared-analyzer/blob/main/tag_protocol.py),
including the lack of a CRC.

No ``pulseio`` import — safe on CPython, CircuitPython 10.x, and MicroPython.

Wire-frame timing constants (all times in microseconds):

- Preamble: 3000 mark, 6000 space, 3000 mark
- Bit mark = 2000 µs for both 0 and 1
- Bit space zero = 1000 µs, bit space one = 2000 µs
- Data format: 2-bit team, 3-bit player, 2-bit damage (7 bits total, MSB-first,
  preceded by a single zero padding bit)
- Error tolerance: ±500 µs
"""

from array import array

from hardware.shared.ir_protocol import InfraredDecoder, InfraredEncoder

try:
    from typing import Final
except ImportError:
    pass  # typing not available on all embedded runtimes

# ---------------------------------------------------------------------------
# Wire-frame timing constants (µs)
# ---------------------------------------------------------------------------

TAG_ERROR_MARGIN: Final = 500  # Maximum allowed timing deviation
TAG_PREAMBLE_ERROR_MARGIN: Final = 1000  # Maximum timing deviation for preamble
TAG_PREAMBLE: Final = [3000, 6000, 3000]  # Laser tag start sequence

# Inter-frame idle gap: PulseIn reports the silence between frames as a single
# long space pulse. Longest valid in-frame pulse is the preamble space
# (TAG_PREAMBLE[1] == 6000 µs); anything beyond that plus the error margin
# can only be the trailing gap, never a legitimate frame pulse.
TAG_GAP_THRESHOLD: Final = TAG_PREAMBLE[1] + TAG_ERROR_MARGIN  # 6500 µs

TAG_MARK: Final = 2000  # Duration of mark (ON) pulse for data bits
TAG_SPACE_ZERO: Final = 1000  # Duration of space (OFF) pulse for bit 0
TAG_SPACE_ONE: Final = 2000  # Duration of space (OFF) pulse for bit 1

# Data field bit lengths
TAG_TEAM_BITS: Final = 2  # 2 bits = 4 teams (0-3)
TAG_PLAYER_BITS: Final = 3  # 3 bits = 8 players (1-8)
TAG_DAMAGE_BITS: Final = 2  # 2 bits = 4 damage levels (1-4)
TAG_DATA_BITS: Final = TAG_TEAM_BITS + TAG_PLAYER_BITS + TAG_DAMAGE_BITS
TAG_TOTAL_PULSES: Final = len(TAG_PREAMBLE) + TAG_DATA_BITS * 2


# ---------------------------------------------------------------------------
# Data layer: TagData value object + byte codec
# ---------------------------------------------------------------------------


class TagData:
    """Infrared tag shot data: team, player, and damage.

    Attributes:
        team: Team number (0-3).
        player: Player number (1-8).
        damage: Damage amount (1-4).
    """

    __slots__ = ("damage", "player", "team")

    def __init__(self, team: int, player: int, damage: int) -> None:
        """Initialize tag data.

        Args:
            team: Team identifier (0-3).
            player: Player identifier (1-8).
            damage: Damage value (1-4).
        """
        self.team = team
        self.player = player
        self.damage = damage


def encode_tag_data(tag_data: TagData) -> bytearray:
    """Encode *tag_data* fields into a single byte.

    Byte format: ``[padding(1)] [team(2)] [player-1(3)] [damage-1(2)]``.

    Args:
        tag_data: Tag information to encode.

    Returns:
        ``bytearray`` of length 1 containing the encoded byte.

    Raises:
        ValueError: If ``team``, ``player``, or ``damage`` is out of range.
    """
    if tag_data.team < 0 or tag_data.team > 3:
        raise ValueError("Team must be between 0 and 3.")
    if tag_data.player < 1 or tag_data.player > 8:
        raise ValueError("Player must be between 1 and 8.")
    if tag_data.damage < 1 or tag_data.damage > 4:
        raise ValueError("Damage must be between 1 and 4.")

    byte = (tag_data.team & 0b11) << 5
    byte |= ((tag_data.player - 1) & 0b111) << 2
    byte |= (tag_data.damage - 1) & 0b11

    return bytearray([byte])


def decode_tag_data(data: bytes | bytearray) -> TagData:
    """Decode the first byte of *data* into a :class:`TagData`.

    Byte format: ``[padding(1)] [team(2)] [player-1(3)] [damage-1(2)]``. Bits
    are masked, so every byte decodes to an in-range ``TagData``.

    Args:
        data: Buffer containing at least one byte of encoded tag information.

    Returns:
        Decoded tag shot information.

    Raises:
        ValueError: If *data* is empty.
    """
    if len(data) < 1:
        raise ValueError("Expecting 1 byte of tag data.")

    byte = data[0]
    team = (byte >> 5) & 0b11
    player = 1 + ((byte >> 2) & 0b111)
    damage = 1 + (byte & 0b11)

    return TagData(team, player, damage)


# ---------------------------------------------------------------------------
# Wire layer: TagInfraredEncoder / TagInfraredDecoder
# ---------------------------------------------------------------------------


class TagInfraredEncoder(InfraredEncoder):
    """Infrared tag IR encoder.

    Encodes a single tag-data byte as the preamble followed by 7 data bits
    (MSB-first), each bit being a mark (always ``TAG_MARK``) followed by a
    space (``TAG_SPACE_ZERO`` for 0, ``TAG_SPACE_ONE`` for 1). The byte's
    padding bit (bit 7) is dropped.
    """

    def encode(self, data: bytes | bytearray) -> array:
        """Encode *data* into a infrared tag IR pulse array.

        Args:
            data: Buffer containing at least one byte of encoded tag
                information; only the first byte is used.

        Returns:
            ``array.array('H', …)`` of pulse durations in microseconds,
            starting with the preamble and alternating mark/space for each
            data bit.
        """
        durations = array("H", bytearray(TAG_TOTAL_PULSES * 2))

        idx = 0
        for pulse in TAG_PREAMBLE:
            durations[idx] = pulse
            idx += 1

        # Shift left by 1 to drop the padding bit and align the MSB at 0x80.
        value = (data[0] << 1) & 0xFF
        for _ in range(TAG_DATA_BITS):
            durations[idx] = TAG_MARK
            idx += 1
            durations[idx] = TAG_SPACE_ONE if value & 0x80 else TAG_SPACE_ZERO
            idx += 1
            value = (value << 1) & 0xFF

        return durations


class TagInfraredDecoder(InfraredDecoder):
    """Infrared tag IR decoder.

    Stateful pulse-by-pulse decoder. Feed each received pulse duration (µs)
    to :meth:`decode`; it returns a single-byte ``bytearray`` payload when a
    complete packet has been received, or ``None`` otherwise.
    """

    __slots__ = ()

    def __init__(self) -> None:
        super().__init__(TAG_ERROR_MARGIN)

    def decode(self, pulse: int) -> bytearray | None:
        """Process one pulse and return the decoded byte when a packet completes.

        States:
        - ``0`` to ``len(TAG_PREAMBLE) - 1``: validate preamble pulses;
          reset on mismatch.
        - ``len(TAG_PREAMBLE)`` to ``TAG_TOTAL_PULSES - 1``: decode data
          bits, alternating between a mark pulse and a space pulse (the
          space determines the bit value). The space pulse that completes
          the final data bit (the 17th pulse overall) finalises the packet
          in this same call — no trailing pulse is consumed or awaited.

        A pulse at or beyond ``TAG_GAP_THRESHOLD`` is the inter-frame idle gap
        (``PulseIn`` reports the silence between frames as one long space),
        not frame data — checked first, ahead of the state machine, so it
        always wins over any in-progress decode.

        Args:
            pulse: Pulse duration in microseconds.

        Returns:
            Single-byte ``bytearray`` payload on successful decode; ``None``
            otherwise.
        """
        if pulse >= TAG_GAP_THRESHOLD:
            self._reset(self._max_error_margin)
            return None

        state = self._decoder_state

        if state < len(TAG_PREAMBLE):
            if self._check_pulse(pulse, TAG_PREAMBLE[state], TAG_PREAMBLE_ERROR_MARGIN):
                self._decoder_state += 1
                if self._decoder_state == len(TAG_PREAMBLE):
                    self.packets_started += 1
            else:
                self.preamble_reject += 1
                self._reset(self._max_error_margin)
        else:
            # state < TAG_TOTAL_PULSES: decode data bits. The decoder always
            # finalises and resets on the 17th pulse below, so state can
            # never reach or exceed TAG_TOTAL_PULSES on entry.
            bit_index = state - len(TAG_PREAMBLE)
            if bit_index % 2 == 0:
                if self._check_pulse(pulse, TAG_MARK):
                    self._decoder_state += 1
                else:
                    self.mark_reject += 1
                    self._reset(self._max_error_margin)
                    return None
            else:
                if self._check_pulse(pulse, TAG_SPACE_ONE):
                    self._write_bit(1)
                elif self._check_pulse(pulse, TAG_SPACE_ZERO):
                    self._write_bit(0)
                else:
                    self.space_reject += 1
                    self._reset(self._max_error_margin)
                    return None
                self._decoder_state += 1
                if self._decoder_state == TAG_TOTAL_PULSES:
                    # Last data bit's space just landed (17th pulse). Add the
                    # padding bit so the 7 data bits flush into a byte, then
                    # drop the padding bit by shifting right.
                    self._write_bit(0)
                    tag_byte = self._received_data[0] >> 1
                    saved_margin = self._max_error_margin
                    self.packets_completed += 1
                    self._reset(saved_margin)
                    return bytearray([tag_byte])

        return None
