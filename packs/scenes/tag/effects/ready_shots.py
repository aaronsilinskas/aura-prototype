"""Tag scene "ready_shots" effect — three shot sounds announcing a live blaster.

No pixel output — issued with ``add_effect`` so it
layers over the existing ``scene.ready`` laser sweep without a pixel conflict.
The three shots are a single pre-baked clip, keeping the declarative
one-clip-per-verb audio model intact rather than introducing a rule-driven
sequencer.
"""

from effects.effect import AudioPlaybackConfig, EffectAudio, EffectVerb
from engine.effects.builder import ComposedEffectBuilder

BUILD = ComposedEffectBuilder(
    audio=EffectAudio(
        clips={
            EffectVerb.START: AudioPlaybackConfig(name="scene.ready_shots_start", loop=False),
        }
    ),
)
