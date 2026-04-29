import pytest

from effects.palette import Palette, PaletteLUT256

# ---------------------------------------------------------------------------
# Palette.pack_rgb
# ---------------------------------------------------------------------------


def test_pack_rgb_places_each_channel_in_correct_byte_position() -> None:
    assert Palette.pack_rgb(0x11, 0x22, 0x33) == 0x112233


def test_pack_rgb_produces_zero_when_all_channels_are_zero() -> None:
    assert Palette.pack_rgb(0, 0, 0) == 0


def test_pack_rgb_produces_full_white_when_all_channels_are_max() -> None:
    assert Palette.pack_rgb(255, 255, 255) == 0xFFFFFF


# ---------------------------------------------------------------------------
# PaletteLUT256 — boundary lookups
# ---------------------------------------------------------------------------


def test_lut_lookup_returns_first_stop_color_at_zero() -> None:
    palette = PaletteLUT256(bytes([0, 255, 0, 0, 255, 0, 0, 255]))  # red → blue

    assert palette.lookup(0.0) == Palette.pack_rgb(255, 0, 0)


def test_lut_lookup_returns_last_stop_color_at_one() -> None:
    palette = PaletteLUT256(bytes([0, 255, 0, 0, 255, 0, 0, 255]))  # red → blue

    assert palette.lookup(1.0) == Palette.pack_rgb(0, 0, 255)


def test_lut_lookup_clamps_below_zero_to_first_entry() -> None:
    palette = PaletteLUT256(bytes([0, 255, 0, 0, 255, 0, 0, 255]))  # red → blue

    assert palette.lookup(-0.5) == palette.lookup(0.0)


def test_lut_lookup_clamps_above_one_to_last_entry() -> None:
    palette = PaletteLUT256(bytes([0, 255, 0, 0, 255, 0, 0, 255]))  # red → blue

    assert palette.lookup(1.5) == palette.lookup(1.0)


# ---------------------------------------------------------------------------
# PaletteLUT256 — interpolation
# ---------------------------------------------------------------------------


def test_lut_lookup_interpolates_linearly_between_stops() -> None:
    # black (0,0,0) → white (255,255,255): each channel should track the LUT index
    palette = PaletteLUT256(bytes([0, 0, 0, 0, 255, 255, 255, 255]))

    # index = int(value * 255); weight = index/255 → each channel = index
    assert palette.lookup(0.25) == Palette.pack_rgb(63, 63, 63)  # index 63
    assert palette.lookup(0.5) == Palette.pack_rgb(127, 127, 127)  # index 127
    assert palette.lookup(0.75) == Palette.pack_rgb(191, 191, 191)  # index 191


def test_lut_midpoint_stop_is_set_exactly() -> None:
    # black → red (at index 128) → blue: lookup at exactly 128/255 hits the mid-stop
    palette = PaletteLUT256(bytes([0, 0, 0, 0, 128, 255, 0, 0, 255, 0, 0, 255]))

    assert palette.lookup(128 / 255) == Palette.pack_rgb(255, 0, 0)


def test_lut_with_three_stops_each_segment_has_correct_endpoint_colors() -> None:
    # black → red (at index 128) → blue: verify first and last stops
    palette = PaletteLUT256(bytes([0, 0, 0, 0, 128, 255, 0, 0, 255, 0, 0, 255]))

    assert palette.lookup(0.0) == Palette.pack_rgb(0, 0, 0)
    assert palette.lookup(1.0) == Palette.pack_rgb(0, 0, 255)


# ---------------------------------------------------------------------------
# PaletteLUT256 — edge cases
# ---------------------------------------------------------------------------


def test_lut_with_no_stops_returns_black_for_any_value() -> None:
    palette = PaletteLUT256(b"")

    assert palette.lookup(0.0) == 0
    assert palette.lookup(0.5) == 0
    assert palette.lookup(1.0) == 0


def test_lut_raises_when_stops_length_is_not_a_multiple_of_four() -> None:
    with pytest.raises(ValueError):
        PaletteLUT256(bytes([0, 255, 0]))


def test_lut_auto_anchors_start_with_black_when_first_stop_is_not_at_index_zero() -> (
    None
):
    # Stops begin at index 128 (red); index 0 should be auto-filled with black.
    palette = PaletteLUT256(bytes([128, 255, 0, 0, 255, 0, 255, 0]))

    assert palette.lookup(0.0) == Palette.pack_rgb(0, 0, 0)


def test_lut_auto_anchors_end_with_black_when_last_stop_is_not_at_index_255() -> None:
    # Stops end at index 128 (green); index 255 should be auto-filled with black.
    palette = PaletteLUT256(bytes([0, 255, 0, 0, 128, 0, 255, 0]))

    assert palette.lookup(1.0) == Palette.pack_rgb(0, 0, 0)
