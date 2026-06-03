from effects.effect import Effect, EffectConfig, PixelBuffer
from engine.effects.manager import EffectBuilder


class GreenLightMusic(Effect):
    """Audio-only effect for green light background music.

    Plays via AudioEffectOutput on the AMBIENT scope (voice 0, looping).
    ``renders_pixels = False`` — no pixel buffer is allocated.
    """

    def __init__(self) -> None:
        super().__init__(renders_pixels=False)

    @property
    def name(self) -> str:
        return "rlgl.green_light_music"

    def update(self, elapsed: float) -> None:
        pass

    def render(self, output: PixelBuffer) -> None:
        pass


class GreenLightMusicBuilder(EffectBuilder):
    def __call__(self, name: str, config: EffectConfig) -> GreenLightMusic:
        return GreenLightMusic()


BUILD = GreenLightMusicBuilder()
