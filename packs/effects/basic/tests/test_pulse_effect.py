"""Tests for PulseEffect — what it adds to the single-layer renderer: the ``PEAK`` verb."""

from __future__ import annotations

from effects.effect import EffectConfig, EffectVerb


def _config(options: dict | None = None, listeners: list | None = None) -> EffectConfig:
    return EffectConfig(resolution=16, options=options or {}, listeners=listeners or [])


def _build(options: dict | None = None, listeners: list | None = None):
    from packs.effects.basic.pulse import BUILD

    return BUILD("basic.pulse", _config(options, listeners))


# --- PulseEffect emits PEAK when the brighten phase ends ---


def test_pulse_effect_declares_peak_as_its_only_custom_verb() -> None:
    from packs.effects.basic.helpers.pulse_effect import PulseEffect

    assert PulseEffect.VERBS == (PulseEffect.PEAK,)


def test_pulse_effect_emits_peak_when_the_brighten_phase_ends() -> None:
    from packs.effects.basic.helpers.pulse_effect import PulseEffect

    events: list[EffectVerb] = []
    effect = _build(listeners=[events.append])

    effect.pixels.update(0.6)  # past the default 0.5 s brighten phase → crosses b_on

    assert events == [PulseEffect.PEAK]


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


# --- Listener called on second cycle peak ---


def test_pulse_effect_emits_peak_once_on_the_second_cycle_peak() -> None:
    from packs.effects.basic.helpers.pulse_effect import PulseEffect

    events: list[EffectVerb] = []
    effect = _build(listeners=[events.append])

    effect.pixels.update(2.0)  # full cycle, no peak
    events.clear()
    effect.pixels.update(0.6)  # second cycle crosses b_on
    assert events == [PulseEffect.PEAK]
