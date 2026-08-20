"""Tests for NeoPixelEffectOutput — single-scope NeoPixel strip routing.

The single-scope case is the degenerate one-segment-covering-[0, count] shape.
Uses in-memory fake strips to verify routing; no neopixel hardware import needed.
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


def _make_output(scope_key: str = "personal", count: int = 5):
    """Build a NeoPixelEffectOutput with a mock strip (single full-strip segment)."""
    from hardware.circuitpython.neopixel_output import NeoPixelEffectOutput

    strip = _make_strip(count)
    scope_pixels = {scope_key: range(0, count)}
    output = NeoPixelEffectOutput(strip, scope_pixels)
    return output, strip


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------


def test_scopes_contains_the_configured_scope_key() -> None:
    output, _ = _make_output(scope_key="personal")
    assert len(output.scopes) == 1
    assert output.scopes[0].keys[0] == "personal"


def test_scope_is_a_leaf_with_one_routing_key() -> None:
    """The scope ScopeValue has exactly one routing key so effects target one strip."""
    output, _ = _make_output()
    assert len(output.scopes[0].keys) == 1


def test_min_resolution_equals_strip_count() -> None:
    output, _ = _make_output(count=10)
    assert output.min_resolution == 10


# ---------------------------------------------------------------------------
# create_buffer
# ---------------------------------------------------------------------------


def test_create_buffer_returns_pixel_buffer_sized_to_strip_count() -> None:
    output, _ = _make_output(count=8)
    buf = output.create_buffer("personal")
    assert isinstance(buf, PixelBuffer)
    assert len(buf) == 8


# ---------------------------------------------------------------------------
# update_pixels — routing to the strip
# ---------------------------------------------------------------------------


def test_update_pixels_writes_buffer_to_strip() -> None:
    output, strip = _make_output(count=3)

    buf = PixelBuffer(3)
    buf[0] = 0xFF0000
    buf[1] = 0x00FF00
    buf[2] = 0x0000FF

    output.update_pixels("personal", buf)

    strip.__setitem__.assert_has_calls([call(0, 0xFF0000), call(1, 0x00FF00), call(2, 0x0000FF)])


def test_update_pixels_does_not_write_to_unrelated_strip() -> None:
    from hardware.circuitpython.neopixel_output import NeoPixelEffectOutput

    strip_a = _make_strip(3)
    strip_b = _make_strip(2)
    output_a = NeoPixelEffectOutput(strip_a, {"personal": range(0, 3)})
    NeoPixelEffectOutput(strip_b, {"directional": range(0, 2)})  # independent instance

    buf = PixelBuffer(3)
    output_a.update_pixels("personal", buf)

    strip_b.__setitem__.assert_not_called()


def test_update_pixels_writes_the_single_buffer_verbatim() -> None:
    """update_pixels writes the single already-composed buffer verbatim (no picking/scaling)."""
    output, strip = _make_output(count=2)

    buf = PixelBuffer(2)
    buf[0] = 0xAAAAAA
    buf[1] = 0xBBBBBB

    output.update_pixels("personal", buf)

    strip.__setitem__.assert_has_calls([call(0, 0xAAAAAA), call(1, 0xBBBBBB)])


def test_neopixel_effect_output_constructs_without_brightness_argument() -> None:
    """NeoPixelEffectOutput takes only strip and scope_pixels -- no brightness param."""
    from hardware.circuitpython.neopixel_output import NeoPixelEffectOutput

    strip = _make_strip(1)

    # Must not raise TypeError for a missing brightness argument.
    NeoPixelEffectOutput(strip, {"personal": range(0, 1)})


# ---------------------------------------------------------------------------
# clear_pixels
# ---------------------------------------------------------------------------


def test_clear_pixels_writes_zeros_to_strip() -> None:
    output, strip = _make_output(count=3)

    output.clear_pixels("personal")

    strip.__setitem__.assert_has_calls([call(0, 0), call(1, 0), call(2, 0)])


def test_clear_pixels_does_not_touch_unrelated_strip() -> None:
    from hardware.circuitpython.neopixel_output import NeoPixelEffectOutput

    strip_personal = _make_strip(3)
    strip_directional = _make_strip(2)
    NeoPixelEffectOutput(strip_personal, {"personal": range(0, 3)})
    output_b = NeoPixelEffectOutput(strip_directional, {"directional": range(0, 2)})

    output_b.clear_pixels("directional")

    strip_personal.__setitem__.assert_not_called()


# ---------------------------------------------------------------------------
# flush — delegates to strip.show()
# ---------------------------------------------------------------------------


def test_flush_calls_show_on_its_strip() -> None:
    output, strip = _make_output()

    output.flush()

    strip.show.assert_called_once()


def test_flush_on_one_instance_does_not_show_another_instances_strip() -> None:
    from hardware.circuitpython.neopixel_output import NeoPixelEffectOutput

    strip_a = _make_strip(3)
    strip_b = _make_strip(2)
    output_a = NeoPixelEffectOutput(strip_a, {"personal": range(0, 3)})
    NeoPixelEffectOutput(strip_b, {"directional": range(0, 2)})

    output_a.flush()

    strip_b.show.assert_not_called()
