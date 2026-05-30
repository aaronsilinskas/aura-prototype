from effects.render import Effect, EffectConfig, PixelBuffer
from engine.effects.manager import EffectBuilder, EffectOutput
from engine.events import EffectEvent
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
        self, event: EffectEvent, scope_keys: frozenset[str], receipt: EffectReceipt
    ) -> None:
        self.handle_event_calls.append((event, scope_keys, receipt))

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


class _NamedEffect(Effect):
    """Minimal Effect stub that stores a name and does nothing."""

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
    """Returns a minimal Effect for any effect name."""

    def __call__(self, name: str, config: EffectConfig) -> Effect:
        return _NamedEffect(name)


class SpyEffect:
    """Minimal effect that counts how many times ``update`` was called."""

    renders_pixels: bool = True

    def __init__(self) -> None:
        self.update_count: int = 0

    def update(self, elapsed: float) -> None:
        self.update_count += 1

    def render(self, buf: object) -> None:
        pass


class SpyEffectBuilder(EffectBuilder):
    """Builder that records each effect it creates, for update-count assertions."""

    def __init__(self) -> None:
        self.created: list[SpyEffect] = []

    def __call__(self, name: str, config: EffectConfig) -> SpyEffect:
        effect = SpyEffect()
        self.created.append(effect)
        return effect


class CapturingEffectBuilder(EffectBuilder):
    """Builder that captures the last ``EffectConfig`` it received."""

    def __init__(self) -> None:
        self.last_config: EffectConfig | None = None

    def __call__(self, name: str, config: EffectConfig) -> Effect:
        self.last_config = config
        return _NamedEffect(name)


class EventFiringEffectBuilder(EffectBuilder):
    """Builder that creates an effect which fires a named event on each update."""

    def __init__(self, event_name: str) -> None:
        self._event_name = event_name

    def __call__(self, name: str, config: EffectConfig) -> Effect:
        event_name = self._event_name

        class _EventEffect(Effect):
            @property
            def name(self) -> str:  # type: ignore[override]
                return name

            def update(self, elapsed: float) -> None:
                config.notify_listeners(event_name)

            def render(self, output: object) -> None:
                pass

        return _EventEffect()
