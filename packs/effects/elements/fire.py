from effects.effect import Effect
from effects.palette import PaletteLUT256
from effects.render import EffectRenderer, RendererConfig
from effects.steps.flame import flame
from engine.effects.manager import EffectBuilder

# fmt: off
fire_palette = bytes([0, 32, 0, 0,
                      32, 128, 0, 0,
                      92, 234, 35, 0,
                      128, 255, 128, 0,
                      192, 242, 85, 0,
                      255, 216, 0, 0])
# fmt: on


class FireBuilder(EffectBuilder):
    def __call__(self, name: str, config: RendererConfig) -> EffectRenderer:
        """Classic flickering flame in deep red, orange, and golden yellow —
        turbulent with bright peaks and dark, smoldering roots.

        Level: more sparks and faster heat produce a taller, brighter, and more
        turbulent flame.
        """
        fire_effect = Effect("fire").add_steps(
            [
                flame(
                    spark_count=config.level,
                    resolution=config.resolution,
                    heat_rate=config.level_lerp(1.22, 1.4),
                    extra_cool_rate=0.1,
                    spread=0.3,
                )
            ]
        )

        return EffectRenderer(fire_effect, PaletteLUT256(fire_palette))


BUILD = FireBuilder()
