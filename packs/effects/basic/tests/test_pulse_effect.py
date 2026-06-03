"""Tests for PulseEffect — peak event notification and PulseBuilder return type."""

from __future__ import annotations

from effects.effect import EffectConfig, PixelBuffer


def _config(options: dict | None = None, listeners: list | None = None) -> EffectConfig:
    return EffectConfig(resolution=16, options=options or {}, listeners=listeners or [])


def _build(options: dict | None = None, listeners: list | None = None):
    from packs.effects.basic.pulse import BUILD

    return BUILD("basic.pulse", _config(options, listeners))


def _render(effect, pixel_count: int = 4) -> list:
    buf = PixelBuffer(pixel_count)
    effect.pixels.render(buf)
    return list(buf)


# --- PulseEffect calls notify_listeners("peak") when at_peak is True ---


def test_pulse_effect_calls_listener_on_peak() -> None:
    events: list[str] = []
    effect = _build(listeners=[events.append])

    # brighten_duration=0.5; update past b_on
    effect.pixels.update(0.6)

    assert "peak" in events


# --- PulseEffect does NOT call listener when not at peak ---


def test_pulse_effect_no_listener_call_during_brighten() -> None:
    events: list[str] = []
    effect = _build(listeners=[events.append])

    effect.pixels.update(0.2)  # still in brighten, hasn't crossed b_on

    assert events == []


def test_pulse_effect_no_listener_call_during_on_phase_after_peak() -> None:
    events: list[str] = []
    effect = _build(listeners=[events.append])

    effect.pixels.update(0.6)  # peak tick
    events.clear()
    effect.pixels.update(0.1)  # still in ON, no new peak
    assert events == []


def test_pulse_effect_no_listener_call_during_darken() -> None:
    events: list[str] = []
    effect = _build(listeners=[events.append])

    effect.pixels.update(0.6)  # crosses b_on → peak fires
    events.clear()
    effect.pixels.update(0.8)  # into darken phase, no new crossing
    assert events == []


def test_pulse_effect_no_listener_call_during_off() -> None:
    events: list[str] = []
    effect = _build(listeners=[events.append])

    effect.pixels.update(0.6)  # crosses b_on
    events.clear()
    effect.pixels.update(1.3)  # into off phase (elapsed=1.9), no new crossing
    assert events == []


# --- PulseEffect with no listeners fires without error ---


def test_pulse_effect_peak_with_no_listeners_is_silent() -> None:
    effect = _build()  # no listeners
    effect.pixels.update(0.6)  # crosses b_on
    # Should not raise


# --- PulseEffect still renders pixels correctly ---


def test_pulse_effect_renders_pixels_correctly_at_on_phase() -> None:
    effect = _build(options={"start_color": 0x000000, "end_color": 0xFFFFFF})
    effect.pixels.update(0.75)  # mid-ON
    pixels = _render(effect)
    assert all(p == 0xFFFFFF for p in pixels)


# --- Listener called on second cycle peak ---


def test_pulse_effect_listener_called_on_second_cycle_peak() -> None:
    events: list[str] = []
    effect = _build(listeners=[events.append])

    effect.pixels.update(2.0)  # full cycle, no peak
    events.clear()
    effect.pixels.update(0.6)  # second cycle crosses b_on
    assert "peak" in events
