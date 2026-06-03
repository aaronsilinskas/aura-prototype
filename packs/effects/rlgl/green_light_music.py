from effects.effect import AudioPlaybackConfig, Effect, EffectAudio, EffectConfig
from engine.effects.manager import EffectBuilder


class _Builder(EffectBuilder):
    def __call__(self, name: str, config: EffectConfig) -> Effect:
        return Effect(
            name=name,
            audio=EffectAudio(
                clips={"start": AudioPlaybackConfig(name=name + "_start", loop=True)}
            ),
        )


BUILD = _Builder()
