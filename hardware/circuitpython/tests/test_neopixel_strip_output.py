"""Tests for NeoPixelEffectOutput with multi-segment (scope_pixels) routing.

Verifies that a single physical strip can be subdivided into scope segments,
each segment acts on only its own pixel range, and brightness multiplies
correctly.  Uses in-memory fake strips to avoid hardware imports.
"""

from __future__ import annotations

from unittest.mock import MagicMock, call

from effects.effect import PixelBuffer

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_strip(count: int) -> MagicMock:
    """Return a mock NeoPixel strip with list-like pixel interface."""
    strip = MagicMock()
    strip.__len__ = MagicMock(return_value=count)
    return strip


def _make_receipt(brightness: float = 1.0) -> MagicMock:
    receipt = MagicMock()
    receipt.brightness = brightness
    return receipt


def _make_segmented_output(
    scope_pixels: dict,
    count: int = 30,
    brightness: float = 1.0,
):
    """Build a NeoPixelEffectOutput with a mock strip and given scope_pixels."""
    from hardware.circuitpython.neopixel_output import NeoPixelEffectOutput

    strip = _make_strip(count)
    output = NeoPixelEffectOutput(strip, scope_pixels, brightness)
    return output, strip


# ---------------------------------------------------------------------------
# Construction: scopes and min_resolution
# ---------------------------------------------------------------------------


def test_scopes_contains_one_scope_value_per_segment() -> None:
    """NeoPixelEffectOutput.scopes has one ScopeValue per scope_pixels entry."""
    scope_pixels = {"personal": range(0, 10), "ambient": range(10, 30)}
    output, _ = _make_segmented_output(scope_pixels, count=30)

    assert len(output.scopes) == 2


def test_scopes_expose_all_configured_scope_keys() -> None:
    """Each scope key in scope_pixels appears in output.scopes."""
    scope_pixels = {"personal": range(0, 10), "ambient": range(10, 30)}
    output, _ = _make_segmented_output(scope_pixels, count=30)

    all_keys = {sv.keys[0] for sv in output.scopes}
    assert all_keys == {"personal", "ambient"}


def test_min_resolution_is_length_of_longest_segment() -> None:
    """min_resolution is the length of the longest segment (not total strip count)."""
    scope_pixels = {"personal": range(0, 10), "ambient": range(10, 30)}
    output, _ = _make_segmented_output(scope_pixels, count=30)

    # ambient is 20 pixels; personal is 10 pixels
    assert output.min_resolution == 20


def test_single_full_strip_segment_min_resolution_equals_count() -> None:
    """For a single segment covering the whole strip, min_resolution == count."""
    scope_pixels = {"personal": range(0, 10)}
    output, _ = _make_segmented_output(scope_pixels, count=10)

    assert output.min_resolution == 10


# ---------------------------------------------------------------------------
# create_buffer: sized to segment length, not strip length
# ---------------------------------------------------------------------------


def test_create_buffer_for_segment_is_sized_to_segment_length() -> None:
    """create_buffer returns a PixelBuffer sized to the segment, not the whole strip."""
    scope_pixels = {"personal": range(0, 10), "ambient": range(10, 30)}
    output, _ = _make_segmented_output(scope_pixels, count=30)

    buf = output.create_buffer("personal")
    assert isinstance(buf, PixelBuffer)
    assert len(buf) == 10


def test_create_buffer_for_larger_segment_returns_correct_size() -> None:
    """create_buffer for the larger segment uses that segment's length."""
    scope_pixels = {"personal": range(0, 10), "ambient": range(10, 30)}
    output, _ = _make_segmented_output(scope_pixels, count=30)

    buf = output.create_buffer("ambient")
    assert len(buf) == 20


# ---------------------------------------------------------------------------
# update_pixels: writes only the named segment's pixel range
# ---------------------------------------------------------------------------


def test_update_pixels_writes_buffer_to_correct_strip_offsets() -> None:
    """update_pixels writes each buffer pixel to the segment's offset in the strip."""
    scope_pixels = {"personal": range(0, 3), "ambient": range(3, 6)}
    output, strip = _make_segmented_output(scope_pixels, count=6)

    buf = PixelBuffer(3)
    buf[0] = 0xFF0000
    buf[1] = 0x00FF00
    buf[2] = 0x0000FF

    output.update_pixels("personal", [buf], [_make_receipt()])

    strip.__setitem__.assert_has_calls([call(0, 0xFF0000), call(1, 0x00FF00), call(2, 0x0000FF)])


def test_update_pixels_for_second_segment_writes_at_correct_offset() -> None:
    """update_pixels for ambient segment writes at strip index 10, not 0."""
    scope_pixels = {"personal": range(0, 10), "ambient": range(10, 20)}
    output, strip = _make_segmented_output(scope_pixels, count=20)

    buf = PixelBuffer(10)
    buf[0] = 0xAABBCC

    output.update_pixels("ambient", [buf], [_make_receipt()])

    # First write must be at strip index 10
    first_call = strip.__setitem__.call_args_list[0]
    assert first_call == call(10, 0xAABBCC)


def test_update_pixels_does_not_write_outside_segment_range() -> None:
    """update_pixels for personal segment does not write to ambient's indices."""
    scope_pixels = {"personal": range(0, 5), "ambient": range(5, 10)}
    output, strip = _make_segmented_output(scope_pixels, count=10)

    buf = PixelBuffer(5)
    output.update_pixels("personal", [buf], [_make_receipt()])

    written_indices = {c.args[0] for c in strip.__setitem__.call_args_list}
    # Must only write to 0..4 — not 5..9
    assert all(i < 5 for i in written_indices)


def test_update_pixels_go_dark_writes_zeros_to_segment_only() -> None:
    """update_pixels with empty buffers zeros only the segment's range."""
    scope_pixels = {"personal": range(2, 5)}
    output, strip = _make_segmented_output(scope_pixels, count=6)

    output.update_pixels("personal", [], [])

    strip.__setitem__.assert_has_calls([call(2, 0), call(3, 0), call(4, 0)])
    written_indices = {c.args[0] for c in strip.__setitem__.call_args_list}
    assert written_indices == {2, 3, 4}


# ---------------------------------------------------------------------------
# update_pixels: brightness
# ---------------------------------------------------------------------------


def test_update_pixels_applies_receipt_brightness() -> None:
    """update_pixels scales each pixel by the receipt brightness."""
    scope_pixels = {"personal": range(0, 1)}
    output, strip = _make_segmented_output(scope_pixels, count=1)

    buf = PixelBuffer(1)
    buf[0] = 0xFF0000

    output.update_pixels("personal", [buf], [_make_receipt(brightness=0.5)])

    strip.__setitem__.assert_called_once_with(0, 0x7F0000)


def test_update_pixels_applies_strip_brightness() -> None:
    """update_pixels scales each pixel by the per-strip brightness config."""
    scope_pixels = {"personal": range(0, 1)}
    output, strip = _make_segmented_output(scope_pixels, count=1, brightness=0.5)

    buf = PixelBuffer(1)
    buf[0] = 0xFF0000

    output.update_pixels("personal", [buf], [_make_receipt(brightness=1.0)])

    strip.__setitem__.assert_called_once_with(0, 0x7F0000)


def test_update_pixels_multiplies_strip_and_receipt_brightness() -> None:
    """update_pixels multiplies strip brightness by receipt brightness."""
    scope_pixels = {"personal": range(0, 1)}
    output, strip = _make_segmented_output(scope_pixels, count=1, brightness=0.5)

    buf = PixelBuffer(1)
    buf[0] = 0xFF0000

    output.update_pixels("personal", [buf], [_make_receipt(brightness=0.5)])

    # 0xFF * 0.25 = 63 = 0x3F
    strip.__setitem__.assert_called_once_with(0, 0x3F0000)


# ---------------------------------------------------------------------------
# clear_pixels: zeros only the named segment
# ---------------------------------------------------------------------------


def test_clear_pixels_zeros_the_named_segment() -> None:
    """clear_pixels writes zero only to the segment's pixel range."""
    scope_pixels = {"personal": range(0, 3), "ambient": range(3, 6)}
    output, strip = _make_segmented_output(scope_pixels, count=6)

    output.clear_pixels("personal")

    strip.__setitem__.assert_has_calls([call(0, 0), call(1, 0), call(2, 0)])
    written_indices = {c.args[0] for c in strip.__setitem__.call_args_list}
    assert written_indices == {0, 1, 2}


def test_clear_pixels_for_second_segment_writes_at_correct_offset() -> None:
    """clear_pixels for the ambient segment clears only indices in that range."""
    scope_pixels = {"personal": range(0, 5), "ambient": range(5, 10)}
    output, strip = _make_segmented_output(scope_pixels, count=10)

    output.clear_pixels("ambient")

    written_indices = {c.args[0] for c in strip.__setitem__.call_args_list}
    assert written_indices == {5, 6, 7, 8, 9}


# ---------------------------------------------------------------------------
# flush: calls strip.show() once
# ---------------------------------------------------------------------------


def test_flush_calls_show_on_the_strip() -> None:
    """flush() calls show() on the strip."""
    scope_pixels = {"personal": range(0, 10)}
    output, strip = _make_segmented_output(scope_pixels, count=10)

    output.flush()

    strip.show.assert_called_once()


# ---------------------------------------------------------------------------
# Single-segment full-strip case (backward compatibility)
# ---------------------------------------------------------------------------


def test_single_full_strip_segment_update_pixels_writes_all_pixels() -> None:
    """A single segment covering the whole strip writes all pixels correctly."""
    scope_pixels = {"personal": range(0, 3)}
    output, strip = _make_segmented_output(scope_pixels, count=3)

    buf = PixelBuffer(3)
    buf[0] = 0x111111
    buf[1] = 0x222222
    buf[2] = 0x333333

    output.update_pixels("personal", [buf], [_make_receipt()])

    strip.__setitem__.assert_has_calls([call(0, 0x111111), call(1, 0x222222), call(2, 0x333333)])


def test_single_full_strip_segment_clear_pixels_zeros_all() -> None:
    """clear_pixels on a single full-strip segment zeros all pixels."""
    scope_pixels = {"personal": range(0, 3)}
    output, strip = _make_segmented_output(scope_pixels, count=3)

    output.clear_pixels("personal")

    strip.__setitem__.assert_has_calls([call(0, 0), call(1, 0), call(2, 0)])
