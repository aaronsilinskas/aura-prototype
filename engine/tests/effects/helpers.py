from effects.render import EffectRenderer, PixelBuffer, RendererConfig
from engine.effects.manager import EffectBuilder, EffectOutput
from engine.state import EffectReceipt


class SpyEffectOutput(EffectOutput):
    """Test spy that captures every ``update_pixels`` call for assertion."""

    def __init__(self, min_resolution: int, scopes: list, receives_pixels: bool = True) -> None:
        super().__init__(receives_pixels=receives_pixels)
        self.min_resolution = min_resolution
        self.scopes = scopes
        self.update_pixels_calls: list = []
        self.created_buffers: list = []
        self.create_buffer_key_calls: list = []
        self.handle_event_calls: list = []
        self.flush_calls: list = []
        self.clear_pixels_calls: list = []

    def handle_event(
        self, event_name: str, scope_keys: frozenset[str], receipt: EffectReceipt
    ) -> None:
        self.handle_event_calls.append((event_name, scope_keys, receipt))

    def create_buffer(self, scope_key: str) -> PixelBuffer:
        buf = PixelBuffer(self.min_resolution)
        self.created_buffers.append(buf)
        self.create_buffer_key_calls.append(scope_key)
        return buf

    def update_pixels(self, scope_key: str, buffers: list, receipts: list) -> None:
        self.update_pixels_calls.append((scope_key, list(zip(buffers, receipts))))

    def flush(self) -> None:
        self.flush_calls.append(True)

    def clear_pixels(self, scope_key: str) -> None:
        self.clear_pixels_calls.append(scope_key)


class _NamedRenderer(EffectRenderer):
    """Minimal EffectRenderer stub that stores a name and does nothing."""

    def __init__(self, name: str) -> None:
        self._name = name

    @property
    def name(self) -> str:
        return self._name

    def update(self, elapsed: float) -> None:
        pass

    def render(self, output: object) -> None:
        pass


class StubEffectBuilder(EffectBuilder):
    """Returns a minimal EffectRenderer for any effect name."""

    def __call__(self, name: str, config: RendererConfig) -> EffectRenderer:
        return _NamedRenderer(name)


class SpyRenderer:
    """Minimal renderer that counts how many times ``update`` was called."""

    renders_pixels: bool = True

    def __init__(self) -> None:
        self.update_count: int = 0

    def update(self, elapsed: float) -> None:
        self.update_count += 1

    def render(self, buf: object) -> None:
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
        return _NamedRenderer(name)


class EventFiringEffectBuilder(EffectBuilder):
    """Builder that creates a renderer which fires a named event on each update."""

    def __init__(self, event_name: str) -> None:
        self._event_name = event_name

    def __call__(self, name: str, config: RendererConfig) -> EffectRenderer:
        event_name = self._event_name

        class _EventRenderer(EffectRenderer):
            @property
            def name(self) -> str:  # type: ignore[override]
                return name

            def update(self, elapsed: float) -> None:
                config.notify_listeners(event_name)

            def render(self, output: object) -> None:
                pass

        return _EventRenderer()
