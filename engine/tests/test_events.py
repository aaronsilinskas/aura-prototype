"""EffectEvent identity: ``pack``, ``name`` and ``verb``; the Resolved clip is payload."""

from __future__ import annotations

from effects.effect import AudioPlaybackConfig, ResolvedClip
from engine.events import EffectEvent

_CLIP = ResolvedClip(AudioPlaybackConfig("sfx.boom", loop=False), "/sounds/boom.wav")


def test_effect_events_differing_only_in_clip_are_equal_and_hash_alike() -> None:
    with_clip = EffectEvent("sfx", "bang", "start", _CLIP)
    without_clip = EffectEvent("sfx", "bang", "start")

    assert with_clip == without_clip
    assert hash(with_clip) == hash(without_clip)


def test_effect_event_repr_leaves_out_the_clip() -> None:
    assert repr(EffectEvent("sfx", "bang", "start", _CLIP)) == "EffectEvent('sfx', 'bang', 'start')"


def test_effect_event_without_a_clip_argument_has_no_clip() -> None:
    assert EffectEvent("sfx", "bang", "start").clip is None
