from effects.effect import Effect, EffectConfig, EffectPixels, PixelBuffer
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
        self, event: EffectEvent, scope_keys: frozenset[str], effect: Effect, receipt: EffectReceipt
    ) -> None:
        self.handle_event_calls.append((event, scope_keys, effect, receipt))

    def create_buffer(self, scope_key: str) -> PixelBuffer:
        buf = PixelBuffer(self.min_resolution)
        self.created_buffers.append(buf)
        self.create_buffer_key_calls.append(scope_key)
        return buf

    def update_pixels(self, scope_key: str, buffer: PixelBuffer) -> None:
        self.update_pixels_calls.append((scope_key, buffer))

    def flush(self) -> None:
        self.flush_calls.append(True)

    def clear_pixels(self, scope_key: str) -> None:
        self.clear_pixels_calls.append(scope_key)


class _StubPixels(EffectPixels):
    """A no-op pixel compositor for testing."""

    def update(self, elapsed: float) -> None:
        pass

    def render(self, output: object) -> None:
        pass


class StubEffectBuilder(EffectBuilder):
    """Returns a minimal Effect with pixels for any effect name."""

    def __call__(self, name: str, config: EffectConfig) -> Effect:
        return Effect(name=name, pixels=_StubPixels())


class SpyEffect(EffectPixels):
    """Minimal EffectPixels that counts how many times ``update`` was called."""

    def __init__(self) -> None:
        self.update_count: int = 0

    def update(self, elapsed: float) -> None:
        self.update_count += 1

    def render(self, buf: object) -> None:
        pass


class SpyEffectBuilder(EffectBuilder):
    """Builder that records each SpyEffect it creates, for update-count assertions."""

    def __init__(self) -> None:
        self.created: list[SpyEffect] = []

    def __call__(self, name: str, config: EffectConfig) -> Effect:
        effect = SpyEffect()
        self.created.append(effect)
        return Effect(name=name, pixels=effect)


class CapturingEffectBuilder(EffectBuilder):
    """Builder that captures the last ``EffectConfig`` it received."""

    def __init__(self) -> None:
        self.last_config: EffectConfig | None = None

    def __call__(self, name: str, config: EffectConfig) -> Effect:
        self.last_config = config
        return Effect(name=name, pixels=_StubPixels())


class ColorFillEffectBuilder(EffectBuilder):
    """Builder whose effect renders a solid color into whatever buffer it is given.

    Fills every slot up to the buffer's current logical length, so it reflects
    a `MergeStrategy`'s ``prepare_buffers`` sizing (e.g. Split's per-effect
    partition) rather than the buffer's full allocated capacity.
    """

    def __init__(self, color: int) -> None:
        self._color = color

    def __call__(self, name: str, config: EffectConfig) -> Effect:
        color = self._color

        class _ColorFillPixels(EffectPixels):
            def update(self, elapsed: float) -> None:
                pass

            def render(self, buf: PixelBuffer) -> None:
                for i in range(len(buf)):
                    buf[i] = color

        return Effect(name=name, pixels=_ColorFillPixels())


class RenderLengthProbeEffectBuilder(EffectBuilder):
    """Builder whose effect records the buffer length seen at each ``render`` call.

    Used to confirm a `MergeStrategy`'s ``prepare_buffers`` sizing already
    happened by the time ``render`` runs.
    """

    def __init__(self) -> None:
        self.observed_lengths: list[int] = []

    def __call__(self, name: str, config: EffectConfig) -> Effect:
        observed = self.observed_lengths

        class _ProbePixels(EffectPixels):
            def update(self, elapsed: float) -> None:
                pass

            def render(self, buf: PixelBuffer) -> None:
                observed.append(len(buf))

        return Effect(name=name, pixels=_ProbePixels())


class EventFiringEffectBuilder(EffectBuilder):
    """Builder that creates an effect which fires a named event on each update."""

    def __init__(self, event_name: str) -> None:
        self._event_name = event_name

    def __call__(self, name: str, config: EffectConfig) -> Effect:
        event_name = self._event_name

        class _EventPixels(EffectPixels):
            def update(self, elapsed: float) -> None:
                config.notify_listeners(event_name)

            def render(self, output: object) -> None:
                pass

        return Effect(name=name, pixels=_EventPixels())
