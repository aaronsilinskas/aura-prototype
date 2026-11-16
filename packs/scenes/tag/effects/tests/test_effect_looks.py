"""Which Tag effects keep a fixed look and which take the caller's options."""

from __future__ import annotations

from effects.effect import Effect, EffectConfig, PixelBuffer
from packs.scenes.tag.effects import ammo_empty, fire_shot, hit, warning_pulse

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


def _warning_pulse(pulse_duration: float) -> Effect:
    return warning_pulse.BUILD(
        "scene.warning_pulse",
        EffectConfig(resolution=4, options={"pulse_duration": pulse_duration}),
    )


def test_warning_pulse_fades_from_black_to_white() -> None:
    effect = _warning_pulse(0.6)

    assert _render(effect) == [0x000000] * 4
    assert _render(effect, elapsed=0.3) == [0xFFFFFF] * 4


def test_warning_pulse_spends_half_its_duration_brightening_and_half_darkening() -> None:
    half_gray = [0x7F7F7F] * 4

    assert _render(_warning_pulse(2.0), elapsed=0.5) == half_gray
    assert _render(_warning_pulse(2.0), elapsed=1.0) == [0xFFFFFF] * 4
    assert _render(_warning_pulse(2.0), elapsed=1.5) == half_gray
