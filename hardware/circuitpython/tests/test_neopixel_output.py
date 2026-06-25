"""Tests for NeoPixelEffectOutput — single-scope NeoPixel strip routing.

One NeoPixelEffectOutput per scope; no neopixel hardware import in the
routing logic. Uses in-memory fake strips to verify routing.
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


def _make_output(scope_key: str = "personal", count: int = 5, brightness: float = 1.0):
    """Build a NeoPixelEffectOutput with a mock strip."""
    from hardware.circuitpython.neopixel_output import NeoPixelEffectOutput

    strip = _make_strip(count)
    output = NeoPixelEffectOutput(scope_key, strip, count, brightness)
    return output, strip


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------


def test_scopes_contains_the_configured_scope_key() -> None:
    """NeoPixelEffectOutput.scopes contains a single ScopeValue for its scope."""
    output, _ = _make_output(scope_key="personal")
    assert len(output.scopes) == 1
    assert output.scopes[0].keys[0] == "personal"


def test_scope_is_a_leaf_with_one_routing_key() -> None:
    """The scope ScopeValue has exactly one routing key so effects target one strip."""
    output, _ = _make_output()
    assert len(output.scopes[0].keys) == 1


def test_min_resolution_equals_strip_count() -> None:
    """min_resolution equals the configured strip count."""
    output, _ = _make_output(count=10)
    assert output.min_resolution == 10


# ---------------------------------------------------------------------------
# create_buffer
# ---------------------------------------------------------------------------


def test_create_buffer_returns_pixel_buffer_sized_to_strip_count() -> None:
    """create_buffer returns a PixelBuffer sized to the strip's pixel count."""
    output, _ = _make_output(count=8)
    buf = output.create_buffer("personal")
    assert isinstance(buf, PixelBuffer)
    assert len(buf) == 8


# ---------------------------------------------------------------------------
# update_pixels — routing to the strip
# ---------------------------------------------------------------------------


def test_update_pixels_writes_buffer_to_strip() -> None:
    """update_pixels writes each pixel from the buffer to the strip."""
    output, strip = _make_output(count=3)

    buf = PixelBuffer(3)
    buf[0] = 0xFF0000
    buf[1] = 0x00FF00
    buf[2] = 0x0000FF

    receipt = MagicMock()
    receipt.brightness = 1.0
    output.update_pixels("personal", [buf], [receipt])

    strip.__setitem__.assert_has_calls([call(0, 0xFF0000), call(1, 0x00FF00), call(2, 0x0000FF)])


def test_update_pixels_does_not_write_to_unrelated_strip() -> None:
    """A second independent output's strip is not touched by the first's update_pixels."""
    from hardware.circuitpython.neopixel_output import NeoPixelEffectOutput

    strip_a = _make_strip(3)
    strip_b = _make_strip(2)
    output_a = NeoPixelEffectOutput("personal", strip_a, 3)
    NeoPixelEffectOutput("directional", strip_b, 2)  # independent instance

    buf = PixelBuffer(3)
    receipt = MagicMock()
    receipt.brightness = 1.0
    output_a.update_pixels("personal", [buf], [receipt])

    strip_b.__setitem__.assert_not_called()


def test_update_pixels_uses_last_buffer_when_multiple_buffers() -> None:
    """update_pixels composites by using the last (topmost) buffer."""
    output, strip = _make_output(count=2)

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


def test_update_pixels_applies_receipt_brightness_scaling() -> None:
    """update_pixels scales each pixel by the receipt brightness."""
    output, strip = _make_output(count=1)

    buf = PixelBuffer(1)
    buf[0] = 0xFF0000  # pure red

    receipt = MagicMock()
    receipt.brightness = 0.5
    output.update_pixels("personal", [buf], [receipt])

    # 0xFF * 0.5 = 127 = 0x7F
    strip.__setitem__.assert_called_once_with(0, 0x7F0000)


def test_update_pixels_applies_scope_brightness() -> None:
    """update_pixels scales each pixel by the per-scope brightness config."""
    output, strip = _make_output(count=1, brightness=0.5)

    buf = PixelBuffer(1)
    buf[0] = 0xFF0000  # pure red

    receipt = MagicMock()
    receipt.brightness = 1.0
    output.update_pixels("personal", [buf], [receipt])

    # 0xFF * 0.5 = 0x7F
    strip.__setitem__.assert_called_once_with(0, 0x7F0000)


def test_update_pixels_multiplies_scope_and_receipt_brightness() -> None:
    """update_pixels multiplies scope brightness by receipt brightness (not adds them)."""
    output, strip = _make_output(count=1, brightness=0.5)

    buf = PixelBuffer(1)
    buf[0] = 0xFF0000  # pure red

    receipt = MagicMock()
    receipt.brightness = 0.5
    output.update_pixels("personal", [buf], [receipt])

    # 0xFF * (0.5 * 0.5) = 0xFF * 0.25 = 63 = 0x3F
    strip.__setitem__.assert_called_once_with(0, 0x3F0000)


def test_update_pixels_go_dark_writes_zeros() -> None:
    """update_pixels with empty buffers writes zeros to the strip (go-dark signal)."""
    output, strip = _make_output(count=2)

    output.update_pixels("personal", [], [])

    strip.__setitem__.assert_has_calls([call(0, 0), call(1, 0)])


# ---------------------------------------------------------------------------
# clear_pixels
# ---------------------------------------------------------------------------


def test_clear_pixels_writes_zeros_to_strip() -> None:
    """clear_pixels writes zero to every pixel slot in the strip."""
    output, strip = _make_output(count=3)

    output.clear_pixels("personal")

    strip.__setitem__.assert_has_calls([call(0, 0), call(1, 0), call(2, 0)])


def test_clear_pixels_does_not_touch_unrelated_strip() -> None:
    """clear_pixels on one instance does not affect a second independent instance's strip."""
    from hardware.circuitpython.neopixel_output import NeoPixelEffectOutput

    strip_personal = _make_strip(3)
    strip_directional = _make_strip(2)
    NeoPixelEffectOutput("personal", strip_personal, 3)
    output_b = NeoPixelEffectOutput("directional", strip_directional, 2)

    output_b.clear_pixels("directional")

    strip_personal.__setitem__.assert_not_called()


# ---------------------------------------------------------------------------
# flush — delegates to strip.show()
# ---------------------------------------------------------------------------


def test_flush_calls_show_on_its_strip() -> None:
    """flush() calls show() on the instance's strip."""
    output, strip = _make_output()

    output.flush()

    strip.show.assert_called_once()


def test_flush_on_one_instance_does_not_show_another_instances_strip() -> None:
    """flush() on one instance does not trigger show() on a second independent instance."""
    from hardware.circuitpython.neopixel_output import NeoPixelEffectOutput

    strip_a = _make_strip(3)
    strip_b = _make_strip(2)
    output_a = NeoPixelEffectOutput("personal", strip_a, 3)
    NeoPixelEffectOutput("directional", strip_b, 2)

    output_a.flush()

    strip_b.show.assert_not_called()
