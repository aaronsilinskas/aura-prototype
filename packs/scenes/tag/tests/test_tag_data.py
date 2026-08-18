"""Behaviour-driven tests for the tag scene's data codec.

Covers:
- TagData value object (slots, no dataclasses)
- encode_tag_data / decode_tag_data round-trip and validation
"""

import pytest

from packs.scenes.tag.tag_data import TagData, decode_tag_data, encode_tag_data

# ---------------------------------------------------------------------------
# TagData value object
# ---------------------------------------------------------------------------


def test_tag_data_stores_team_player_and_damage():
    tag = TagData(team=2, player=5, damage=3)

    assert tag.team == 2
    assert tag.player == 5
    assert tag.damage == 3


def test_tag_data_uses_slots_with_no_instance_dict():
    tag = TagData(team=0, player=1, damage=1)

    assert not hasattr(tag, "__dict__")


# ---------------------------------------------------------------------------
# encode_tag_data / decode_tag_data
# ---------------------------------------------------------------------------


def test_minimum_tag_data_encodes_to_zero_byte():
    assert encode_tag_data(TagData(team=0, player=1, damage=1)) == bytearray([0x00])


@pytest.mark.parametrize("team", range(4))
@pytest.mark.parametrize("player", range(1, 9))
@pytest.mark.parametrize("damage", range(1, 5))
def test_encode_decode_round_trips_for_all_valid_field_values(team, player, damage):
    tag = TagData(team=team, player=player, damage=damage)

    decoded = decode_tag_data(encode_tag_data(tag))

    assert decoded.team == team
    assert decoded.player == player
    assert decoded.damage == damage


@pytest.mark.parametrize(
    "team, player, damage",
    [
        (-1, 1, 1),
        (4, 1, 1),
        (0, 0, 1),
        (0, 9, 1),
        (0, 1, 0),
        (0, 1, 5),
    ],
)
def test_encode_raises_for_out_of_range_fields(team, player, damage):
    tag = TagData(team=team, player=player, damage=damage)

    with pytest.raises(ValueError):
        encode_tag_data(tag)


def test_decode_raises_for_empty_data():
    with pytest.raises(ValueError):
        decode_tag_data(b"")
