"""Unit tests for packs.effects.rlgl.warning_sting.

Pulse behaviour (peak events, rendering, validation) is covered by
test_pulse_effect.py.  These tests only verify what is specific to
warning_sting: that BUILD passes the given name through to the effect so that
AudioEffectOutput can resolve ``warning_sting_peak.wav`` via the name-based
sound path lookup.
"""

from __future__ import annotations

from effects.effect import EffectConfig


def _config() -> EffectConfig:
    return EffectConfig(level=10, resolution=16, options={}, listeners=[])


def test_warning_sting_build_preserves_effect_name() -> None:
    from packs.effects.rlgl.warning_sting import BUILD

    effect = BUILD("warning_sting", _config())
    assert effect.name == "warning_sting"
