from effects.effect import Effect
from effects.palette import PaletteLUT256
from effects.render import EffectRenderer, PixelBuffer, RendererConfig
from effects.steps.control import call
from engine.effects.manager import EffectBuilder, EffectOutput
from engine.state import EffectReceipt


class SpyEffectOutput(EffectOutput):
    """Test spy that captures every ``update_pixels`` call for assertion."""

    def __init__(self, min_resolution: int, scopes: list) -> None:
        self.min_resolution = min_resolution
        self.scopes = scopes
        self.update_pixels_calls: list = []
        self.created_buffers: list = []
        self.create_buffer_key_calls: list = []
        self.handle_event_calls: list = []
        self.show_pixels_calls: list = []

    def handle_event(
        self, event_name: str, scope_keys: frozenset[str], receipt: EffectReceipt
    ) -> None:
        self.handle_event_calls.append((event_name, scope_keys, receipt))

    def create_buffer(self, scope_key: str) -> PixelBuffer:
        buf = PixelBuffer(self.min_resolution)
        self.created_buffers.append(buf)
        self.create_buffer_key_calls.append(scope_key)
        return buf

    def update_pixels(self, frames: list[tuple[PixelBuffer, EffectReceipt]]) -> None:
        self.update_pixels_calls.append(list(frames))

    def show_pixels(self) -> None:
        self.show_pixels_calls.append(True)


class StubEffectBuilder(EffectBuilder):
    """Returns a minimal EffectRenderer for any effect name."""

    def __call__(self, name: str, config: RendererConfig) -> EffectRenderer:
        return EffectRenderer(Effect(name), PaletteLUT256(b""))


class SpyRenderer:
    """Minimal renderer that counts how many times ``update`` was called."""

    def __init__(self) -> None:
        self.update_count: int = 0

    def update(self, state: object, timer: object) -> None:
        self.update_count += 1

    def render(self, state: object, buf: object) -> None:
        pass


class SpyEffectBuilder(EffectBuilder):
    """Builder that records each renderer it creates, for update-count assertions."""

    def __init__(self) -> None:
        self.created: list[SpyRenderer] = []

    def __call__(self, name: str, config: RendererConfig) -> SpyRenderer:
        renderer = SpyRenderer()
        self.created.append(renderer)
        return renderer


class CapturingEffectBuilder(EffectBuilder):
    """Builder that captures the last ``RendererConfig`` it received."""

    def __init__(self) -> None:
        self.last_config: RendererConfig | None = None

    def __call__(self, name: str, config: RendererConfig) -> EffectRenderer:
        self.last_config = config
        return EffectRenderer(Effect(name), PaletteLUT256(b""))


class EventFiringEffectBuilder(EffectBuilder):
    """Builder that creates a renderer which fires a named event on each update."""

    def __init__(self, event_name: str) -> None:
        self._event_name = event_name

    def __call__(self, name: str, config: RendererConfig) -> EffectRenderer:
        event_name = self._event_name
        step = call(lambda state, timer: config.notify_listeners(event_name))
        effect = Effect(name).add_steps([step])
        return EffectRenderer(effect, PaletteLUT256(b""))
