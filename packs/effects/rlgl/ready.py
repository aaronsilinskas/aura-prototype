from effects.effect import AudioPlaybackConfig, Effect, EffectAudio, EffectConfig
from engine.effects.manager import EffectBuilder
from packs.effects.elements.water import WaterBuilder

_water = WaterBuilder()


class _Builder(EffectBuilder):
    def __call__(self, name: str, config: EffectConfig) -> Effect:
        base = _water(name, config)
        return Effect(
            name=base.name,
            pixels=base.pixels,
            audio=EffectAudio(
                clips={"start": AudioPlaybackConfig(name=name + "_start", loop=False)}
            ),
        )


BUILD = _Builder()
