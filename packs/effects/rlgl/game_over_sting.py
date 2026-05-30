from effects.render import EffectRenderer, PixelBuffer, RendererConfig
from engine.effects.manager import EffectBuilder


class GameOverStingRenderer(EffectRenderer):
    """Audio-only renderer for the game over sting sound effect.

    Plays via AudioEffectOutput on the PERSONAL scope (voice 1, one-shot).
    ``renders_pixels = False`` — no pixel buffer is allocated.
    """

    def __init__(self) -> None:
        super().__init__(renders_pixels=False)

    @property
    def name(self) -> str:
        return "rlgl.game_over_sting"

    def update(self, elapsed: float) -> None:
        pass

    def render(self, output: PixelBuffer) -> None:
        pass


class GameOverStingBuilder(EffectBuilder):
    def __call__(self, name: str, config: RendererConfig) -> GameOverStingRenderer:
        return GameOverStingRenderer()


BUILD = GameOverStingBuilder()
