"""Unit tests for packs.effects.elements.lightning."""

from __future__ import annotations

import random

from effects.effect import Effect, EffectConfig, EffectVerb
from packs.effects.elements.lightning import BUILD, LightningEffect

# Longer than any bolt's idle or strike phase at any level, so one update of this
# length moves every bolt across exactly one phase boundary.
_PAST_ANY_PHASE = 10.0


def _build(level: int, events: list[EffectVerb]) -> Effect:
    random.seed(1323)
    config = EffectConfig(resolution=16, options={"level": level}, listeners=[events.append])
    return BUILD("elements.lightning", config)


def _update(effect: Effect, elapsed: float) -> None:
    assert effect.pixels is not None
    effect.pixels.update(elapsed)


def test_lightning_declares_strike_as_its_only_custom_verb() -> None:
    effect = _build(level=1, events=[])

    assert effect.emitted_verbs() == (EffectVerb.START, EffectVerb.STOP, LightningEffect.STRIKE)


def test_lightning_notifies_strike_in_an_update_where_its_bolt_strikes() -> None:
    events: list[EffectVerb] = []
    effect = _build(level=1, events=events)

    _update(effect, _PAST_ANY_PHASE)

    assert events == [LightningEffect.STRIKE]


def test_lightning_notifies_strike_once_when_several_bolts_strike_in_the_same_update() -> None:
    events: list[EffectVerb] = []
    effect = _build(level=10, events=events)  # level 10 builds five bolts

    _update(effect, _PAST_ANY_PHASE)

    assert events == [LightningEffect.STRIKE]


def test_lightning_does_not_notify_strike_in_an_update_where_no_bolt_strikes() -> None:
    events: list[EffectVerb] = []
    effect = _build(level=10, events=events)

    _update(effect, 0.0)

    assert events == []


def test_lightning_does_not_notify_strike_when_its_bolts_end_their_strike() -> None:
    events: list[EffectVerb] = []
    effect = _build(level=10, events=events)
    _update(effect, _PAST_ANY_PHASE)  # every bolt strikes
    events.clear()

    _update(effect, _PAST_ANY_PHASE)  # every bolt ends its strike and goes idle

    assert events == []
