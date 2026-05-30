from effects.render import Effect, EffectConfig, PixelBuffer
from engine.effects.manager import EffectBuilder


class WarningSting(Effect):
    """Audio-only effect for the warning sting sound effect.

    Plays via AudioEffectOutput on the PERSONAL scope (voice 1, one-shot).
    ``renders_pixels = False`` — no pixel buffer is allocated.
    """

    def __init__(self) -> None:
        super().__init__(renders_pixels=False)

    @property
    def name(self) -> str:
        return "rlgl.warning_sting"

    def update(self, elapsed: float) -> None:
        pass

    def render(self, output: PixelBuffer) -> None:
        pass


class WarningStingBuilder(EffectBuilder):
    def __call__(self, name: str, config: EffectConfig) -> WarningSting:
        return WarningSting()


BUILD = WarningStingBuilder()
