from effects.effect import AudioPlaybackConfig, Effect, EffectAudio, EffectConfig
from engine.effects.manager import EffectBuilder

_GREEN_LIGHT_MUSIC_AUDIO = EffectAudio(
    clips={"start": AudioPlaybackConfig(name="scene.green_light_music_start", loop=True)}
)


class _Builder(EffectBuilder):
    def __call__(self, name: str, config: EffectConfig) -> Effect:
        return Effect(
            name=name,
            audio=_GREEN_LIGHT_MUSIC_AUDIO,
        )


BUILD = _Builder()
