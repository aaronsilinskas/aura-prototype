"""Tag scene "ready_shots" effect — three shot sounds announcing a live blaster.

No pixel output (``Effect.pixels = None``) — issued with ``add_effect`` so it
layers over the existing ``scene.ready`` laser sweep without a pixel conflict.
One-shot with ``stops_effect=True`` so the effect ends when the clip finishes.
The three shots are a single pre-baked clip, keeping the declarative
one-clip-per-verb audio model intact rather than introducing a rule-driven
sequencer.
"""

from __future__ import annotations

from effects.effect import (
    AudioPlaybackConfig,
    Effect,
    EffectAudio,
    EffectConfig,
)
from engine.effects.manager import EffectBuilder

_READY_SHOTS_AUDIO = EffectAudio(
    clips={
        "start": AudioPlaybackConfig(name="scene.ready_shots_start", loop=False, stops_effect=True),
    }
)


class _Builder(EffectBuilder):
    def __call__(self, name: str, config: EffectConfig) -> Effect:
        return Effect(
            name=name,
            pixels=None,
            audio=_READY_SHOTS_AUDIO,
        )


BUILD = _Builder()
