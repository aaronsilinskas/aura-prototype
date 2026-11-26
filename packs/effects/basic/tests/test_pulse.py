from __future__ import annotations

import pytest

from effects.effect import EffectConfig, PixelBuffer


def _config(options: dict | None = None) -> EffectConfig:
    opts = dict(options) if options else {}
    return EffectConfig(resolution=16, options=opts)


def _build(options: dict | None = None):
    from packs.effects.basic.pulse import BUILD

    return BUILD("basic.pulse", _config(options))


def _render(effect, pixel_count: int = 4) -> list:
    buf = PixelBuffer(pixel_count)
    effect.pixels.render(buf)
    return list(buf)


def test_pulse_effect_name_is_basic_pulse() -> None:
    effect = _build()
    assert effect.name == "basic.pulse"


def test_pulse_stores_start_color_unscaled() -> None:
    effect = _build(
        options={
            "start_color": 0x7F3F1F,
            "end_color": 0x000000,
            "brighten_duration": 0.0,
            "on_duration": 0.0,
            "darken_duration": 0.0,
            "off_duration": 1.0,
        }
    )
    effect.pixels.update(0.5)  # mid-OFF phase → start_color
    pixels = _render(effect)
    assert all(p == 0x7F3F1F for p in pixels)


def test_pulse_stores_end_color_unscaled() -> None:
    effect = _build(
        options={
            "start_color": 0x000000,
            "end_color": 0x7F3F1F,
            "brighten_duration": 0.0,
            "on_duration": 1.0,
        }
    )
    effect.pixels.update(0.5)  # mid-ON phase → end_color
    pixels = _render(effect)
    assert all(p == 0x7F3F1F for p in pixels)


def test_pulse_ignores_brightness_option() -> None:
    effect_with_brightness = _build(
        options={
            "start_color": 0x000000,
            "end_color": 0xFFFFFF,
            "brighten_duration": 0.0,
            "on_duration": 1.0,
            "brightness": 0.5,
        }
    )
    effect_without_brightness = _build(
        options={
            "start_color": 0x000000,
            "end_color": 0xFFFFFF,
            "brighten_duration": 0.0,
            "on_duration": 1.0,
        }
    )
    effect_with_brightness.pixels.update(0.5)
    effect_without_brightness.pixels.update(0.5)

    assert _render(effect_with_brightness) == _render(effect_without_brightness)
    assert all(p == 0xFFFFFF for p in _render(effect_without_brightness))


def test_pulse_default_start_color_is_black() -> None:
    effect = _build()
    effect.pixels.update(0.0)
    assert all(p == 0x000000 for p in _render(effect))


def test_pulse_default_end_color_is_white() -> None:
    effect = _build()
    effect.pixels.update(0.75)  # mid-ON with the default 0.5 s phases
    assert all(p == 0xFFFFFF for p in _render(effect))


def test_pulse_default_durations_make_a_two_second_cycle() -> None:
    # Four default 0.5 s phases: at 2.0 the cycle wraps back to the start color.
    effect = _build(options={"start_color": 0x112233, "end_color": 0xFFFFFF})
    effect.pixels.update(2.0)
    assert all(p == 0x112233 for p in _render(effect))


# Black-to-white, sampled where a phase boundary would sit elsewhere if the
# option fell back to its 0.5 s default.


@pytest.mark.parametrize(
    ("durations", "elapsed", "expected"),
    [
        pytest.param((1.0, 1.0, 0.0, 1.0), 1.5, 0xFFFFFF, id="brighten_duration"),
        pytest.param((0.0, 1.0, 0.0, 1.0), 0.75, 0xFFFFFF, id="on_duration"),
        pytest.param((0.0, 1.0, 1.0, 1.0), 2.5, 0x000000, id="darken_duration"),
        pytest.param((0.0, 1.0, 0.0, 1.0), 1.75, 0x000000, id="off_duration"),
    ],
)
def test_pulse_duration_option_sets_its_phase_length(
    durations: tuple[float, float, float, float], elapsed: float, expected: int
) -> None:
    brighten, on, darken, off = durations
    effect = _build(
        options={
            "start_color": 0x000000,
            "end_color": 0xFFFFFF,
            "brighten_duration": brighten,
            "on_duration": on,
            "darken_duration": darken,
            "off_duration": off,
        }
    )
    effect.pixels.update(elapsed)
    assert all(p == expected for p in _render(effect))


def test_pulse_negative_brighten_duration_raises_value_error() -> None:
    with pytest.raises(ValueError, match="Pulse durations must be non-negative"):
        _build(options={"brighten_duration": -0.1})


def test_pulse_negative_on_duration_raises_value_error() -> None:
    with pytest.raises(ValueError, match="Pulse durations must be non-negative"):
        _build(options={"on_duration": -1.0})


def test_pulse_negative_darken_duration_raises_value_error() -> None:
    with pytest.raises(ValueError, match="Pulse durations must be non-negative"):
        _build(options={"darken_duration": -0.5})


def test_pulse_negative_off_duration_raises_value_error() -> None:
    with pytest.raises(ValueError, match="Pulse durations must be non-negative"):
        _build(options={"off_duration": -0.01})


def test_pulse_all_zero_durations_raises_value_error() -> None:
    with pytest.raises(ValueError, match="At least one pulse phase duration must be non-zero"):
        _build(
            options={
                "brighten_duration": 0.0,
                "on_duration": 0.0,
                "darken_duration": 0.0,
                "off_duration": 0.0,
            }
        )
