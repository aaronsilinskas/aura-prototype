"""NeoPixel current-budget arithmetic -- no board imports, CPython-testable.

Reached only through ``parse_device_config``, which parses the
``neopixel_current_budget`` block and calls :func:`tune_neopixel_brightness`
on the pixel entries it is still building. The tuning rewrites each budgeted
strip's ``brightness`` in place: nothing else holds those strip objects yet,
and no ``DeviceConfig`` exists until parsing returns, which is where the
"a parsed DeviceConfig is never changed" rule starts.
"""

from __future__ import annotations

try:
    from typing import Final
except ImportError:
    pass

from hardware.shared.device_config import (
    MatrixPixelsConfig,
    NeoPixelPixelsConfig,
    NeoPixelScopeConfig,
    NeoPixelStripConfig,
)

__all__ = ["tune_neopixel_brightness"]

# The tuner solves for a limit shrunk by this relative margin so float
# rounding (~1e-16 per operation) can only land the tuned total under the
# real limit, never over -- with no exact-summation primitive on device.
_BUDGET_ROUNDING_MARGIN: Final = 1e-9


def _budgeted_strips(
    pixels: list[MatrixPixelsConfig | NeoPixelPixelsConfig],
) -> list[NeoPixelStripConfig | NeoPixelScopeConfig]:
    """Every strip the current budget counts: enabled NeoPixel entries, both shapes."""
    strips: list[NeoPixelStripConfig | NeoPixelScopeConfig] = []
    for entry in pixels:
        if isinstance(entry, NeoPixelPixelsConfig) and entry.enabled:
            strips.extend(entry.strips)
            strips.extend(entry.scopes.values())
    return strips


def _draw_ma(
    strips: list[NeoPixelStripConfig | NeoPixelScopeConfig], max_pixel_current_ma: int
) -> float:
    """Worst-case draw of *strips* at full white, at their current brightness."""
    total = 0.0
    for strip in strips:
        total += strip.count * strip.brightness * max_pixel_current_ma
    return total


def tune_neopixel_brightness(
    pixels: list[MatrixPixelsConfig | NeoPixelPixelsConfig],
    current_limit_ma: int,
    max_pixel_current_ma: int,
    min_brightness: float,
) -> tuple[float, float, int]:
    """Dim every enabled NeoPixel strip in *pixels* to fit the limit, never below the floor.

    Rewrites each strip's ``brightness`` in place; under the limit, nothing
    changes.

    Returns:
        ``(estimate_ma, scale, at_min_brightness)``: the worst-case draw at
        declared brightness, the factor applied to strips not held at the
        floor (``1.0`` when under the limit), and how many strips were held.

    Raises:
        ValueError: If the strips exceed the limit even at the floor.
    """
    strips = _budgeted_strips(pixels)
    estimate_ma = _draw_ma(strips, max_pixel_current_ma)
    if estimate_ma <= current_limit_ma:
        return estimate_ma, 1.0, 0

    # A strip declared at or below the floor is held as declared, never scaled.
    held = [strip for strip in strips if strip.brightness <= min_brightness]
    unheld = sorted(
        (strip for strip in strips if strip.brightness > min_brightness),
        key=lambda strip: strip.brightness,
    )

    floor_ma = 0.0
    for strip in strips:
        floor_ma += strip.count * min(strip.brightness, min_brightness) * max_pixel_current_ma
    if floor_ma > current_limit_ma:
        raise ValueError(
            f"neopixel_current_budget: NeoPixel strips draw {floor_ma:.1f} mA even at"
            + f" min_brightness {min_brightness}, over current_limit_ma {current_limit_ma} mA"
        )

    # Holding a strip leaves less for the rest, so the shared scale only
    # falls -- the dimmest unheld strip is always the next to cross the
    # floor. Hold strips dimmest-first until the scale keeps the rest above it.
    target_ma = current_limit_ma * (1 - _BUDGET_ROUNDING_MARGIN)
    held_ma = _draw_ma(held, max_pixel_current_ma)
    scale = 1.0
    while unheld:
        scale = max(0.0, (target_ma - held_ma) / _draw_ma(unheld, max_pixel_current_ma))
        dimmest = unheld[0]
        if dimmest.brightness * scale >= min_brightness:
            break
        unheld.pop(0)
        dimmest.brightness = min_brightness
        held_ma += _draw_ma([dimmest], max_pixel_current_ma)
    # An empty `unheld` means the floor current is (within the rounding
    # margin) the limit itself: the floor wins, and the last solved scale
    # is kept for narration.

    for strip in unheld:
        strip.brightness *= scale
    return estimate_ma, scale, len(strips) - len(unheld)
