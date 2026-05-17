from effects.effect import Effect, EffectState, EffectTimer
from effects.manager.scope import ScopeValue
from effects.palette import Palette
from effects.render import EffectRenderer, PixelBuffer, RendererConfig
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


class EffectManager:
    __slots__ = ("_effects", "_seen", "_timer")

    def __init__(self) -> None:
        self._effects: dict[str, list[tuple[EffectRenderer, EffectState]]] = {}
        self._timer: EffectTimer = EffectTimer()
        self._seen: set[int] = set()

    def _notify_listeners(self, event_name: str, scope: ScopeValue) -> None:
        """Notify listeners registered for the given scope."""
        pass
        # for key in scope.keys:
        #    pass
        # TODO - look up outputs in scope and notify them of the event

    def _build_effect(
        self, scope: ScopeValue, name: str, level: int, options: dict
    ) -> "tuple[EffectRenderer, EffectState]":
        """Construct an EffectRenderer paired with a fresh EffectState."""

        # Listeners will need a hook to audio/vibration drivers to trigger
        def scoped_listener(event_name):
            # Event handling -> look up in-scoped EffectOutput and call handle_event(event_name)
            return self._notify_listeners(event_name, scope)

        # resolution = (
        #     16  # TODO - look up max resolution required from effect outputs that match the scope
        # )

        # config = RendererConfig(
        #     level=level, resolution=resolution, options=options, listeners=[scoped_listener]
        # )

        # TODO look up the effect builder in a registry, give it config, and return the result

        return EffectRenderer(Effect(name), Palette()), EffectState()

    def set_effect(self, scope: ScopeValue, name: str, level: int, options: dict) -> None:
        """Replace any running effect(s) in scope and start this one."""
        pair = self._build_effect(scope, name, level, options)
        for key in scope.keys:
            self._effects[key] = [pair]

    def add_effect(self, scope: ScopeValue, name: str, level: int, options: dict) -> None:
        """Layer this effect alongside any running effects in scope.

        If nothing is running in scope, behaves like set_effect.
        The driver determines how layered effects are composited (e.g. splitting an LED strip).
        """
        pair = self._build_effect(scope, name, level, options)
        for key in scope.keys:
            if key in self._effects:
                self._effects[key].append(pair)
            else:
                self._effects[key] = [pair]

    def stop_effect(self, scope: ScopeValue) -> None:
        """Stop all running effects in scope."""
        # TODO - this is a bit brute-force; we could track individual effects and only stop those
        #   that match the scope, but that would add complexity to the data structure and
        #   bookkeeping. For now, we can just stop all effects in any scope that matches.
        for key in scope.keys:
            if key in self._effects:
                del self._effects[key]

    def register_output(
        self, output: EffectOutput, min_resolution: int, scopes: list[ScopeValue]
    ) -> None:
        """Register an output to receive rendered frames for effects in matching scopes."""

        # TODO - just store the params and brute force lookups. Optimize later with dicts!!!!

        # TODO - this will need to trigger some kind of reconciliation to start sending frames for
        #   any existing effects that match the new output's scope
        pass

    def update(self, timer: Timer) -> None:
        """Tick all active effects in each scope."""
        self._timer.update(timer.elapsed)
        seen = self._seen
        seen.clear()
        for effects in self._effects.values():
            for renderer, state in effects:
                renderer_id = id(renderer)
                if renderer_id not in seen:
                    seen.add(renderer_id)
                    renderer.update(state, self._timer)

        # TODO: render to buffers and send to outputs

    def __repr__(self) -> str:
        parts = []
        for key, effects in self._effects.items():
            names = ", ".join(r.name for r, _ in effects)
            parts.append(f"{key}: [{names}]")
        return "\n".join(parts) if parts else "(no active effects)"
