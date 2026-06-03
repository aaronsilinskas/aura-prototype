"""Unit tests for packs.effects.elements.lightning."""

from __future__ import annotations

from effects.effect import EffectConfig, PixelBuffer
from effects.layers.add_samples_renderer import AddSamplesRenderer
from effects.palette import PaletteLUT256
from effects.shape import Shape
from packs.effects.elements.lightning import (
    _LIGHTNING_PALETTE,
    LightningBuilder,
    LightningEffect,
    _LightningBolt,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _config(level: int = 5, listeners=None) -> EffectConfig:
    return EffectConfig(level=level, resolution=16, listeners=listeners or [])


def _make_bolt() -> _LightningBolt:
    shape = Shape.padded(0.25, Shape.centered_gradient())
    return _LightningBolt(shape, hide_max=1.5, strike_duration_min=0.5, strike_duration_max=1.25)


# ---------------------------------------------------------------------------
# _LightningBolt — at_strike initial state
# ---------------------------------------------------------------------------


def test_lightning_bolt_at_strike_initialized_false() -> None:
    bolt = _make_bolt()
    assert bolt.at_strike is False


# ---------------------------------------------------------------------------
# _LightningBolt — at_strike is True only on IDLE→STRIKE transition
# ---------------------------------------------------------------------------


def test_lightning_bolt_at_strike_true_on_idle_to_strike_transition() -> None:
    bolt = _make_bolt()

    bolt.update(10.0)

    assert bolt.at_strike is True


def test_lightning_bolt_at_strike_false_before_idle_threshold_is_crossed() -> None:
    bolt = _make_bolt()

    bolt.update(0.0)

    assert bolt.at_strike is False


def test_lightning_bolt_at_strike_false_during_strike_phase() -> None:
    bolt = _make_bolt()
    bolt.update(10.0)  # advance to STRIKE phase

    bolt.update(0.0)

    assert bolt.at_strike is False


def test_lightning_bolt_at_strike_false_on_strike_to_idle_transition() -> None:
    bolt = _make_bolt()
    bolt.update(10.0)  # IDLE → STRIKE

    bolt.update(10.0)  # STRIKE → IDLE

    assert bolt.at_strike is False


# ---------------------------------------------------------------------------
# LightningBuilder — name is passed through to the effect
# ---------------------------------------------------------------------------


def test_lightning_effect_name_matches_builder_argument() -> None:
    effect = LightningBuilder()("elements.lightning", _config())
    assert effect.name == "elements.lightning"


# ---------------------------------------------------------------------------
# LightningEffect — notify_listeners("strike") on tick with at_strike
# ---------------------------------------------------------------------------


def test_lightning_effect_calls_notify_listeners_when_bolt_strikes() -> None:
    events: list[str] = []
    config = _config(listeners=[events.append])

    shape = Shape.padded(0.25, Shape.centered_gradient())
    bolt = _LightningBolt(shape, 1.5, 0.5, 1.25)
    palette = PaletteLUT256(_LIGHTNING_PALETTE)
    effect = LightningEffect("test", [bolt], palette, config)

    effect.update(10.0)

    assert "strike" in events


def test_lightning_effect_no_notify_when_no_bolt_strikes() -> None:
    events: list[str] = []
    config = _config(listeners=[events.append])

    shape = Shape.padded(0.25, Shape.centered_gradient())
    bolt = _LightningBolt(shape, 1.5, 0.5, 1.25)
    palette = PaletteLUT256(_LIGHTNING_PALETTE)
    effect = LightningEffect("test", [bolt], palette, config)

    effect.update(0.0)

    assert events == []


def test_lightning_effect_emits_single_strike_event_even_when_multiple_bolts_transition() -> None:
    events: list[str] = []
    config = _config(listeners=[events.append])

    shape = Shape.padded(0.25, Shape.centered_gradient())
    bolts = [_LightningBolt(shape, 1.5, 0.5, 1.25) for _ in range(3)]
    palette = PaletteLUT256(_LIGHTNING_PALETTE)
    effect = LightningEffect("test", bolts, palette, config)

    effect.update(10.0)

    assert events.count("strike") == 1


# ---------------------------------------------------------------------------
# LightningEffect — pixel output identical to AddSamplesRenderer
# ---------------------------------------------------------------------------


def test_lightning_effect_pixel_output_matches_add_samples_renderer() -> None:
    shape = Shape.padded(0.25, Shape.centered_gradient())
    palette = PaletteLUT256(_LIGHTNING_PALETTE)

    # Share a single bolt so both renderers operate on identical state
    bolt = _LightningBolt(shape, 1.5, 0.5, 1.25)
    config = _config()
    le = LightningEffect("a", [bolt], palette, config)
    asr = AddSamplesRenderer("b", [bolt], palette)

    bolt.update(10.0)  # advance bolt to STRIKE phase

    out_le = PixelBuffer(16)
    out_asr = PixelBuffer(16)
    le.render(out_le)
    asr.render(out_asr)

    assert list(out_le) == list(out_asr)


# ---------------------------------------------------------------------------
# LightningEffect — no listeners registered is safe (no crash)
# ---------------------------------------------------------------------------


def test_lightning_effect_fires_strike_event_with_no_listeners_silently() -> None:
    config = _config(listeners=[])

    shape = Shape.padded(0.25, Shape.centered_gradient())
    bolt = _LightningBolt(shape, 1.5, 0.5, 1.25)
    palette = PaletteLUT256(_LIGHTNING_PALETTE)
    effect = LightningEffect("test", [bolt], palette, config)

    effect.update(10.0)  # should not raise


# ---------------------------------------------------------------------------
# LightningEffect — pixel output is zero during idle phase
# ---------------------------------------------------------------------------


def test_lightning_effect_pixel_output_is_zero_during_idle_phase() -> None:
    shape = Shape.padded(0.25, Shape.centered_gradient())
    bolt = _LightningBolt(shape, 1.5, 0.5, 1.25)
    palette = PaletteLUT256(_LIGHTNING_PALETTE)
    effect = LightningEffect("test", [bolt], palette, _config())

    out = PixelBuffer(16)
    effect.render(out)

    assert all(px == 0 for px in out)
