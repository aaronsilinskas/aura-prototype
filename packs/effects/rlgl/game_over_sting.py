from effects.effect import Effect, EffectConfig
from engine.effects.manager import EffectBuilder


class GameOverStingBuilder(EffectBuilder):
    def __call__(self, name: str, config: EffectConfig) -> Effect:
        return Effect(name=name)


BUILD = GameOverStingBuilder()
