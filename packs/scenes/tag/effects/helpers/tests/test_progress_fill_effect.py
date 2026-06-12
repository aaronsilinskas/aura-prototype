"""Tests for ProgressFillEffect — self-animating progress-bar fill.

Prior art: ``packs/effects/basic/helpers/progress_effect.py`` (static fill
render) and ``packs/effects/basic/tests/test_pulse_effect.py`` (driving
``update(elapsed)`` across steps).
"""

from __future__ import annotations

from effects.effect import PixelBuffer
from effects.layers.progress_layer import ProgressLayer
from packs.scenes.tag.effects.helpers.progress_fill_effect import ProgressFillEffect


def _render(effect: ProgressFillEffect, pixel_count: int = 4) -> list[int]:
    buf = PixelBuffer(pixel_count)
    effect.render(buf)
    return list(buf)


# --- update(elapsed) advances rendered progress proportionally ---


def test_renders_no_fill_before_any_update() -> None:
    effect = ProgressFillEffect(ProgressLayer(0.0), color=0xFFFFFF, duration=2.0)

    pixels = _render(effect)

    assert pixels == [0x000000, 0x000000, 0x000000, 0x000000]


def test_update_fills_proportionally_to_elapsed_over_duration() -> None:
    effect = ProgressFillEffect(ProgressLayer(0.0), color=0xFFFFFF, duration=2.0)

    effect.update(1.0)  # halfway through the 2.0s duration -> progress 0.5

    pixels = _render(effect)
    # 4 pixels at progress 0.5 -> first 2 fully lit, rest dark
    assert pixels == [0xFFFFFF, 0xFFFFFF, 0x000000, 0x000000]


def test_update_accumulates_elapsed_across_multiple_calls() -> None:
    effect = ProgressFillEffect(ProgressLayer(0.0), color=0xFFFFFF, duration=2.0)

    effect.update(0.5)
    effect.update(0.5)  # total elapsed 1.0s -> progress 0.5

    pixels = _render(effect)
    assert pixels == [0xFFFFFF, 0xFFFFFF, 0x000000, 0x000000]


def test_progress_clamps_and_holds_at_full_past_duration() -> None:
    effect = ProgressFillEffect(ProgressLayer(0.0), color=0xFFFFFF, duration=2.0)

    effect.update(5.0)  # well past duration -> progress clamps to 1.0

    pixels = _render(effect)
    assert pixels == [0xFFFFFF, 0xFFFFFF, 0xFFFFFF, 0xFFFFFF]


def test_progress_remains_clamped_on_subsequent_update_past_duration() -> None:
    effect = ProgressFillEffect(ProgressLayer(0.0), color=0xFFFFFF, duration=2.0)

    effect.update(2.0)  # exactly at duration -> progress 1.0
    effect.update(1.0)  # further elapsed -> never overshoots

    pixels = _render(effect)
    assert pixels == [0xFFFFFF, 0xFFFFFF, 0xFFFFFF, 0xFFFFFF]
