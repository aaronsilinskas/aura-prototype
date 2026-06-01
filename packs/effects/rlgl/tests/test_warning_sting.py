"""Unit tests for packs.effects.rlgl.warning_sting — WarningStingEffect."""

from __future__ import annotations

from effects.render import EffectConfig, PixelBuffer

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _config(options: dict | None = None, listeners: list | None = None) -> EffectConfig:
    return EffectConfig(level=10, resolution=16, options=options or {}, listeners=listeners or [])


def _build(options: dict | None = None, listeners: list | None = None):
    from packs.effects.rlgl.warning_sting import BUILD

    return BUILD("warning_sting", _config(options, listeners))


def _render(effect, pixel_count: int = 4) -> list:
    buf = PixelBuffer(pixel_count)
    effect.render(buf)
    return list(buf)


# ---------------------------------------------------------------------------
# WarningStingEffect — renders_pixels = True
# ---------------------------------------------------------------------------


def test_warning_sting_effect_renders_pixels_true() -> None:
    effect = _build()
    assert effect.renders_pixels is True


# ---------------------------------------------------------------------------
# WarningStingEffect — fires peak listener on each pulse peak
# ---------------------------------------------------------------------------


def test_warning_sting_fires_peak_listener_on_peak() -> None:
    events: list[str] = []
    effect = _build(listeners=[events.append])

    # Default brighten_duration=0.5; update past b_on crosses the peak
    effect.update(0.6)

    assert "peak" in events


def test_warning_sting_no_listener_call_during_brighten() -> None:
    events: list[str] = []
    effect = _build(listeners=[events.append])

    effect.update(0.2)  # still in brighten, hasn't crossed b_on

    assert events == []


def test_warning_sting_peak_with_no_listeners_is_silent() -> None:
    effect = _build()  # no listeners
    effect.update(0.6)  # crosses b_on
    # Should not raise


# ---------------------------------------------------------------------------
# WarningStingEffect — visual output reflects start_color and end_color options
# ---------------------------------------------------------------------------


def test_warning_sting_renders_end_color_at_on_phase() -> None:
    effect = _build(options={"start_color": 0x000000, "end_color": 0xFFFFFF})
    effect.update(0.75)  # mid-ON
    pixels = _render(effect)
    assert all(p == 0xFFFFFF for p in pixels)


def test_warning_sting_renders_start_color_at_off_phase() -> None:
    effect = _build(
        options={
            "start_color": 0x000000,
            "end_color": 0xFFFFFF,
            "brighten_duration": 0.3,
            "on_duration": 0.4,
            "darken_duration": 0.3,
            "off_duration": 0.5,
        }
    )
    # off phase starts at 1.0 — sample well into off
    effect.update(1.2)
    pixels = _render(effect)
    assert all(p == 0x000000 for p in pixels)


def test_warning_sting_respects_end_color_option() -> None:
    """Builder reads end_color option; rendering reflects it at ON phase."""
    effect = _build(options={"end_color": 0xFF0000, "start_color": 0x000000})
    effect.update(0.75)  # mid-ON
    pixels = _render(effect)
    assert all(p == 0xFF0000 for p in pixels)


# ---------------------------------------------------------------------------
# WarningStingBuilder — reads same option keys as PulseBuilder
# ---------------------------------------------------------------------------


def test_warning_sting_builder_reads_timing_options() -> None:
    """Builder reads brighten/on/darken/off durations from options."""
    events: list[str] = []
    opts = {
        "brighten_duration": 0.1,
        "on_duration": 0.0,
        "darken_duration": 0.1,
        "off_duration": 0.0,
    }
    effect = _build(options=opts, listeners=[events.append])

    effect.update(0.15)  # past b_on=0.1

    assert "peak" in events


def test_warning_sting_builder_raises_on_negative_duration() -> None:
    import pytest

    with pytest.raises(ValueError, match="non-negative"):
        _build(options={"brighten_duration": -0.1})


def test_warning_sting_builder_raises_on_zero_total_duration() -> None:
    import pytest

    with pytest.raises(ValueError, match="non-zero"):
        _build(
            options={
                "brighten_duration": 0.0,
                "on_duration": 0.0,
                "darken_duration": 0.0,
                "off_duration": 0.0,
            }
        )
