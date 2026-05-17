from effects.effect import Effect
from effects.manager.manager import EffectBuilder, EffectOutput
from effects.palette import PaletteLUT256
from effects.render import EffectRenderer, PixelBuffer, RendererConfig


class SpyEffectOutput(EffectOutput):
    """Test spy that captures every ``update_pixels`` call for assertion."""

    def __init__(self, min_resolution: int, scopes: list) -> None:
        self.min_resolution = min_resolution
        self.scopes = scopes
        self.update_pixels_calls: list = []
        self.created_buffers: list = []
        self.handle_event_calls: list = []

    def handle_event(self, event_name: str) -> None:
        self.handle_event_calls.append(event_name)

    def create_buffer(self) -> PixelBuffer:
        buf = PixelBuffer(self.min_resolution)
        self.created_buffers.append(buf)
        return buf

    def update_pixels(self, frames: list) -> None:
        self.update_pixels_calls.append(frames)


class StubEffectBuilder(EffectBuilder):
    """Returns a minimal EffectRenderer for any effect name."""

    def __call__(self, name: str, config: RendererConfig) -> EffectRenderer:
        return EffectRenderer(Effect(name), PaletteLUT256(b""))
