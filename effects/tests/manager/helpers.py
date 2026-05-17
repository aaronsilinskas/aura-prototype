from effects.manager.manager import EffectBuilder, EffectOutput
from effects.render import EffectRenderer, PixelBuffer, RendererConfig


class SpyEffectOutput(EffectOutput):
    """Test spy that captures every ``update_pixels`` call for assertion."""

    def __init__(self, min_resolution: int, scopes: list) -> None:
        self.min_resolution = min_resolution
        self.scopes = scopes
        self.update_pixels_calls: list = []

    def create_buffer(self) -> PixelBuffer:
        return PixelBuffer(self.min_resolution)

    def update_pixels(self, frames: list) -> None:
        self.update_pixels_calls.append(frames)


class StubEffectBuilder(EffectBuilder):
    """Minimal EffectBuilder stub. Raises if called — not needed for slice 1."""

    def __call__(self, name: str, config: RendererConfig) -> EffectRenderer:
        raise NotImplementedError("StubEffectBuilder was called unexpectedly")
