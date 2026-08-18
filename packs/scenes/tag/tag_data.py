"""Tag scene data codec: ``TagData`` plus ``encode_tag_data`` / ``decode_tag_data``.

The game-layer payload of a tag shot — team, player, and damage packed into
one opaque byte. This is a different axis from the wire-frame codec in
:mod:`hardware.shared.ir_codecs.tag` (byte ↔ ``TagData`` here, byte ↔ pulses
there); this module is private to the tag scene and imports no hardware code.

No ``pulseio`` import — safe on CPython, CircuitPython 10.x, and MicroPython.
"""


class TagData:
    """Infrared tag shot data: team, player, and damage.

    Attributes:
        team: Team number (0-3).
        player: Player number (1-8).
        damage: Damage amount (1-4).
    """

    __slots__ = ("damage", "player", "team")

    def __init__(self, team: int, player: int, damage: int) -> None:
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
