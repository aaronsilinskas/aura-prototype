"""Tests for NeoPixelEffectOutput — per-scope NeoPixel strip routing.

One NeoPixel strip per configured leaf scope; no neopixel hardware import
in the routing logic. Uses in-memory fake strips to verify routing.
"""

from __future__ import annotations

from unittest.mock import MagicMock, call

from effects.effect import PixelBuffer

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_strip(count: int) -> MagicMock:
    """Return a mock NeoPixel strip with a list-like pixel interface."""
    strip = MagicMock()
    strip.__len__ = MagicMock(return_value=count)
    return strip


def _make_output(scope_strips: dict | None = None, scope_brightnesses: dict | None = None):
    """Build a NeoPixelEffectOutput with mock strips.

    Args:
        scope_strips: Mapping of scope_key -> (mock_strip, pixel_count).
            Defaults to personal=5, directional=3.
        scope_brightnesses: Mapping of scope_key -> brightness float.
            Defaults to 1.0 for all scopes.
    """
    from hardware.circuitpython.neopixel_output import NeoPixelEffectOutput

    if scope_strips is None:
        scope_strips = {
            "personal": (_make_strip(5), 5),
            "directional": (_make_strip(3), 3),
        }
    if scope_brightnesses is None:
        scope_brightnesses = dict.fromkeys(scope_strips, 1.0)

    strips = {key: strip for key, (strip, _) in scope_strips.items()}
    counts = {key: count for key, (_, count) in scope_strips.items()}
    return NeoPixelEffectOutput(strips, counts, scope_brightnesses), strips


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------


def test_scopes_are_the_configured_leaf_scopes() -> None:
    """NeoPixelEffectOutput.scopes lists each configured scope as a ScopeValue."""
    output, _ = _make_output()
    scope_values = output.scopes
    scope_keys = {s.keys[0] for s in scope_values}
    assert scope_keys == {"personal", "directional"}


def test_each_scope_routes_independently_to_its_own_strip() -> None:
    """Each configured scope has exactly one routing key so effects target individual strips."""
    output, _ = _make_output()
    for sv in output.scopes:
        assert len(sv.keys) == 1, f"scope {sv} must be a leaf with one routing key"


def test_min_resolution_is_largest_strip_count() -> None:
    """min_resolution equals the largest configured strip count."""
    output, _ = _make_output(
        scope_strips={
            "personal": (_make_strip(10), 10),
            "directional": (_make_strip(4), 4),
        }
    )
    assert output.min_resolution == 10


def test_min_resolution_single_scope() -> None:
    """min_resolution with one scope equals that strip count."""
    output, _ = _make_output(
        scope_strips={"personal": (_make_strip(7), 7)},
    )
    assert output.min_resolution == 7


# ---------------------------------------------------------------------------
# create_buffer
# ---------------------------------------------------------------------------


def test_create_buffer_returns_pixel_buffer_sized_to_scope_count() -> None:
    """create_buffer returns a PixelBuffer sized to the scope's strip count."""
    output, _ = _make_output(
        scope_strips={
            "personal": (_make_strip(8), 8),
            "directional": (_make_strip(3), 3),
        }
    )
    buf_personal = output.create_buffer("personal")
    buf_directional = output.create_buffer("directional")
    assert isinstance(buf_personal, PixelBuffer)
    assert len(buf_personal) == 8
    assert len(buf_directional) == 3


# ---------------------------------------------------------------------------
# update_pixels — routing each scope's buffer to its strip
# ---------------------------------------------------------------------------


def test_update_pixels_writes_buffer_to_correct_strip() -> None:
    """update_pixels writes each pixel from the buffer to the scope's strip."""
    personal_strip = _make_strip(3)
    strips = {"personal": (personal_strip, 3), "directional": (_make_strip(2), 2)}
    output, _ = _make_output(scope_strips=strips)

    buf = PixelBuffer(3)
    buf[0] = 0xFF0000
    buf[1] = 0x00FF00
    buf[2] = 0x0000FF

    receipt = MagicMock()
    receipt.brightness = 1.0
    output.update_pixels("personal", [buf], [receipt])

    personal_strip.__setitem__.assert_has_calls(
        [call(0, 0xFF0000), call(1, 0x00FF00), call(2, 0x0000FF)]
    )


def test_update_pixels_does_not_write_to_other_scopes_strip() -> None:
    """update_pixels for 'personal' must not touch the 'directional' strip."""
    personal_strip = _make_strip(3)
    directional_strip = _make_strip(2)
    strips = {"personal": (personal_strip, 3), "directional": (directional_strip, 2)}
    output, _ = _make_output(scope_strips=strips)

    buf = PixelBuffer(3)
    receipt = MagicMock()
    receipt.brightness = 1.0
    output.update_pixels("personal", [buf], [receipt])

    directional_strip.__setitem__.assert_not_called()


def test_update_pixels_uses_last_buffer_when_multiple_buffers() -> None:
    """update_pixels composites by using the last (topmost) buffer."""
    strip = _make_strip(2)
    output, _ = _make_output(scope_strips={"personal": (strip, 2)})

    buf1 = PixelBuffer(2)
    buf1[0] = 0x111111
    buf1[1] = 0x222222

    buf2 = PixelBuffer(2)
    buf2[0] = 0xAAAAAA
    buf2[1] = 0xBBBBBB

    receipt = MagicMock()
    receipt.brightness = 1.0
    output.update_pixels("personal", [buf1, buf2], [receipt, receipt])

    strip.__setitem__.assert_has_calls([call(0, 0xAAAAAA), call(1, 0xBBBBBB)])


def test_update_pixels_applies_brightness_scaling() -> None:
    """update_pixels applies the receipt brightness to each pixel."""
    strip = _make_strip(1)
    output, _ = _make_output(scope_strips={"personal": (strip, 1)})

    buf = PixelBuffer(1)
    buf[0] = 0xFF0000  # pure red

    receipt = MagicMock()
    receipt.brightness = 0.5
    output.update_pixels("personal", [buf], [receipt])

    # 0xFF * 0.5 = 127 = 0x7F; green and blue are 0
    strip.__setitem__.assert_called_once_with(0, 0x7F0000)


def test_update_pixels_applies_scope_brightness() -> None:
    """update_pixels combines receipt brightness with per-scope brightness config."""
    strip = _make_strip(1)
    output, _ = _make_output(
        scope_strips={"personal": (strip, 1)},
        scope_brightnesses={"personal": 0.5},
    )

    buf = PixelBuffer(1)
    buf[0] = 0xFF0000  # pure red, full

    receipt = MagicMock()
    receipt.brightness = 1.0
    output.update_pixels("personal", [buf], [receipt])

    # 0xFF * 0.5 scope brightness = 0x7F
    strip.__setitem__.assert_called_once_with(0, 0x7F0000)


def test_update_pixels_applies_combined_scope_and_receipt_brightness() -> None:
    """update_pixels multiplies scope brightness by receipt brightness (not adds them)."""
    strip = _make_strip(1)
    output, _ = _make_output(
        scope_strips={"personal": (strip, 1)},
        scope_brightnesses={"personal": 0.5},
    )

    buf = PixelBuffer(1)
    buf[0] = 0xFF0000  # pure red

    receipt = MagicMock()
    receipt.brightness = 0.5
    output.update_pixels("personal", [buf], [receipt])

    # 0xFF * (0.5 * 0.5) = 0xFF * 0.25 = 63 = 0x3F
    strip.__setitem__.assert_called_once_with(0, 0x3F0000)


def test_update_pixels_go_dark_writes_zeros() -> None:
    """update_pixels with empty buffers writes zeros to the strip (go-dark signal)."""
    strip = _make_strip(2)
    output, _ = _make_output(scope_strips={"personal": (strip, 2)})

    output.update_pixels("personal", [], [])

    strip.__setitem__.assert_has_calls([call(0, 0), call(1, 0)])


# ---------------------------------------------------------------------------
# clear_pixels
# ---------------------------------------------------------------------------


def test_clear_pixels_writes_zeros_to_strip() -> None:
    """clear_pixels writes zero to every pixel slot in the scope's strip."""
    strip = _make_strip(3)
    output, _ = _make_output(scope_strips={"personal": (strip, 3)})

    output.clear_pixels("personal")

    strip.__setitem__.assert_has_calls([call(0, 0), call(1, 0), call(2, 0)])


def test_clear_pixels_does_not_touch_other_scopes_strip() -> None:
    """clear_pixels for 'directional' must not touch the 'personal' strip."""
    personal_strip = _make_strip(3)
    directional_strip = _make_strip(2)
    strips = {"personal": (personal_strip, 3), "directional": (directional_strip, 2)}
    output, _ = _make_output(scope_strips=strips)

    output.clear_pixels("directional")

    personal_strip.__setitem__.assert_not_called()


# ---------------------------------------------------------------------------
# flush — delegates to strip.show() for each strip
# ---------------------------------------------------------------------------


def test_flush_calls_show_on_all_strips() -> None:
    """flush() calls show() on every registered strip."""
    personal_strip = _make_strip(3)
    directional_strip = _make_strip(2)
    strips = {"personal": (personal_strip, 3), "directional": (directional_strip, 2)}
    output, _ = _make_output(scope_strips=strips)

    output.flush()

    personal_strip.show.assert_called_once()
    directional_strip.show.assert_called_once()
