from effects.effect import EffectState, EffectTimer
from effects.render import EffectRenderer, PixelBuffer, RendererConfig
from engine.effects.scope import ScopeValue
from engine.timer import Timer


class EffectOutput:
    """Interface for sending rendered pixels and events to hardware outputs.

    Concrete subclasses must set in their __init__:
      - min_resolution: int  — minimum pixel count needed by this output.
      - scopes: list         — list of ScopeValue this output serves.
    """

    min_resolution: int
    scopes: "list[ScopeValue]"

    def create_buffer(self) -> PixelBuffer:
        """Create a PixelBuffer sized to this output's hardware pixel count."""
        raise NotImplementedError

    def update_pixels(self, frames: list) -> None:
        """Receive rendered frames (list of PixelBuffer) for this output.

        Called every update tick. Receives an empty list when no effects are active
        (signal to go dark).
        """
        pass

    def handle_event(self, event_name: str) -> None:
        """Handle an event triggered by an effect renderer."""
        pass


class EffectBuilder:
    def __call__(self, name: str, config: RendererConfig) -> EffectRenderer:
        """Build an EffectRenderer for the named effect.

        Args:
            name: The registered effect name (e.g. ``"color.flash"``).
            config: Runtime configuration for the render pass. ``config.level``
                carries the universal intensity in ``[1, 10]``; ``config.options``
                carries any effect-specific parameters (e.g. duration, color).
                ``config.resolution`` describes the output hardware.

        Returns:
            A configured ``EffectRenderer`` ready to be paired with an
            ``EffectState`` and advanced each frame.
        """
        raise NotImplementedError


class EffectControls:
    """Read-only effect-control interface exposed to game rules via GameState.

    Provides effect start/stop operations only. The update() tick is
    intentionally excluded so rules cannot advance the effect loop.
    """

    def set_effect(self, scope: ScopeValue, name: str, level: int, options: dict) -> None:
        raise NotImplementedError

    def add_effect(self, scope: ScopeValue, name: str, level: int, options: dict) -> None:
        raise NotImplementedError

    def stop_effect(self, scope: ScopeValue) -> None:
        raise NotImplementedError


class EffectManager(EffectControls):
    class _EffectEntry:
        __slots__ = ("keys", "output_buffers", "renderer", "state")

        def __init__(
            self,
            keys: tuple[str, ...],
            output_buffers: list,
            renderer: EffectRenderer,
            state: EffectState,
        ) -> None:
            self.keys: tuple[str, ...] = keys
            self.output_buffers: list = output_buffers
            self.renderer: EffectRenderer = renderer
            self.state: EffectState = state

        def __repr__(self) -> str:
            return f"_EffectEntry(keys={self.keys!r})"

    __slots__ = ("_builder", "_effects", "_frames", "_output_key_sets", "_outputs", "_timer")

    def __init__(self, builder: EffectBuilder, outputs: list[EffectOutput]) -> None:
        self._builder: EffectBuilder = builder
        self._outputs: list[EffectOutput] = outputs
        self._effects: list = []
        self._timer: EffectTimer = EffectTimer()
        self._output_key_sets: list = [
            frozenset(k for s in o.scopes for k in s.keys) for o in outputs
        ]
        self._frames: list = [[] for _ in outputs]

    def _notify_listeners(self, event_name: str, scope: ScopeValue) -> None:
        """Notify listeners registered for the given scope."""
        scope_keys = set(scope.keys)
        for output in self._outputs:
            for s in output.scopes:
                if any(k in scope_keys for k in s.keys):
                    output.handle_event(event_name)
                    break

    def _build_effect(
        self, scope: ScopeValue, name: str, level: int, options: dict
    ) -> "EffectManager._EffectEntry":
        """Construct an EffectRenderer paired with a fresh EffectState."""

        def scoped_listener(event_name):
            return self._notify_listeners(event_name, scope)

        scope_keys = set(scope.keys)
        resolution = 16
        output_buffers = []
        for i, output in enumerate(self._outputs):
            if any(k in self._output_key_sets[i] for k in scope_keys):
                if output.min_resolution > resolution:
                    resolution = output.min_resolution
                output_buffers.append(output.create_buffer())
            else:
                output_buffers.append(None)
        config = RendererConfig(
            level=level, resolution=resolution, options=options, listeners=[scoped_listener]
        )
        renderer = self._builder(name, config)
        return EffectManager._EffectEntry(scope.keys, output_buffers, renderer, EffectState())

    def _update_output_buffers(self, entry: "_EffectEntry") -> None:
        """Null out pre-allocated buffers for outputs no longer matched by entry.keys."""
        key_set = set(entry.keys)
        for i in range(len(self._outputs)):
            if entry.output_buffers[i] is not None and not any(
                k in self._output_key_sets[i] for k in key_set
            ):
                entry.output_buffers[i] = None

    def set_effect(self, scope: ScopeValue, name: str, level: int, options: dict) -> None:
        """Replace any running effect(s) in scope and start this one."""
        scope_key_set = set(scope.keys)
        new_effects = []
        for entry in self._effects:
            remaining = tuple(k for k in entry.keys if k not in scope_key_set)
            if remaining:
                entry.keys = remaining
                self._update_output_buffers(entry)
                new_effects.append(entry)
        self._effects = new_effects
        self._effects.append(self._build_effect(scope, name, level, options))

    def add_effect(self, scope: ScopeValue, name: str, level: int, options: dict) -> None:
        """Layer this effect alongside any running effects in scope.

        If nothing is running in scope, behaves like set_effect.
        The driver determines how layered effects are composited (e.g. splitting an LED strip).
        """
        self._effects.append(self._build_effect(scope, name, level, options))

    def stop_effect(self, scope: ScopeValue) -> None:
        """Stop all running effects in scope."""
        scope_key_set = set(scope.keys)
        new_effects = []
        for entry in self._effects:
            remaining = tuple(k for k in entry.keys if k not in scope_key_set)
            if remaining:
                entry.keys = remaining
                self._update_output_buffers(entry)
                new_effects.append(entry)
        self._effects = new_effects

    def update(self, timer: Timer) -> None:
        """Tick all active effects and deliver frames to every registered output."""
        self._timer.update(timer.elapsed)

        # Pass 1: advance each renderer once.
        for entry in self._effects:
            entry.renderer.update(entry.state, self._timer)

        # Pass 2: render and deliver to each output using pre-allocated buffers.
        # Outputs whose scopes have no active effects receive [] (go-dark signal).
        for i in range(len(self._outputs)):
            output = self._outputs[i]
            frames = self._frames[i]
            frames.clear()
            for entry in self._effects:
                buf = entry.output_buffers[i]
                if buf is not None:
                    entry.renderer.render(entry.state, buf)
                    frames.append(buf)
            output.update_pixels(frames)

    def __repr__(self) -> str:
        if not self._effects:
            return "(no active effects)"
        return "\n".join(repr(entry) for entry in self._effects)
