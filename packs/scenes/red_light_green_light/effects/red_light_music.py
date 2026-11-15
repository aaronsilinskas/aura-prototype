from effects.effect import AudioPlaybackConfig, EffectAudio, EffectVerb
from engine.effects.builder import ComposedEffectBuilder

BUILD = ComposedEffectBuilder(
    audio=EffectAudio(
        clips={EffectVerb.START: AudioPlaybackConfig(name="scene.red_light_music_start", loop=True)}
    ),
)
