"""Which Tag effects keep a fixed look and which take the caller's options."""

from __future__ import annotations

from effects.effect import Effect, EffectConfig, PixelBuffer
from packs.scenes.tag.effects import ammo_empty, fire_shot, hit

_GREEN = 0x00FF00
_GREEN_PULSE: dict[str, object] = {"start_color": _GREEN, "end_color": _GREEN}


def _render(effect: Effect, elapsed: float = 0.0) -> list[int]:
    assert effect.pixels is not None
    effect.pixels.update(elapsed)
    buf = PixelBuffer(4)
    effect.pixels.render(buf)
    return list(buf)


def test_fire_shot_flashes_white_whatever_color_the_caller_passes() -> None:
    effect = fire_shot.BUILD(
        "scene.fire_shot", EffectConfig(resolution=4, options={"color": _GREEN})
    )

    assert _render(effect) == [0xFFFFFF] * 4


def test_ammo_empty_peaks_red_whatever_colors_the_caller_passes() -> None:
    effect = ammo_empty.BUILD("scene.ammo_empty", EffectConfig(resolution=4, options=_GREEN_PULSE))

    assert _render(effect, elapsed=0.6) == [0xFF0000] * 4


def test_hit_pulses_in_the_colors_the_caller_passes() -> None:
    effect = hit.BUILD("scene.hit", EffectConfig(resolution=4, options=_GREEN_PULSE))

    assert _render(effect) == [_GREEN] * 4
