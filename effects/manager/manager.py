from effects.effect import Effect, EffectState, EffectTimer
from effects.manager.scope import ScopeValue
from effects.palette import Palette
from effects.render import EffectRenderer, RendererConfig
from engine.timer import Timer

# TODO: Need output interfaces that register resolution
# - for each resolution key, have a list of outputs
# - one state machine for each key?
# TODO: sparkle step still uses pixel_count internally — needs manual update


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
        # scope key -> list of active (EffectRenderer, EffectState) pairs
        self._effects: dict[str, list[tuple[EffectRenderer, EffectState]]] = {}
        self._timer: EffectTimer = EffectTimer()
        self._seen: set[int] = set()

    def _build_effect(
        self, name: str, level: int, options: dict
    ) -> "tuple[EffectRenderer, EffectState]":
        """Construct an EffectRenderer paired with a fresh EffectState."""

        # TODO - construct a RendererConfig to pass to the builder:
        # -- resolution will need to come from each driver, but re-use renderer if
        #   those match
        # -- level comes from set/add_effect
        # -- options comes from set/add_effect
        # -- listeners will need a hook to audio/vibration drivers to trigger

        # TODO implement registry to build effect renderer(s) for drivers
        return EffectRenderer(Effect(name), Palette()), EffectState()

    def set_effect(self, scope: ScopeValue, name: str, level: int, options: dict) -> None:
        """Replace any running effect(s) in scope and start this one."""
        pair = self._build_effect(name, level, options)
        for key in scope.keys:
            self._effects[key] = [pair]

    def add_effect(self, scope: ScopeValue, name: str, level: int, options: dict) -> None:
        """Layer this effect alongside any running effects in scope.

        If nothing is running in scope, behaves like set_effect.
        The driver determines how layered effects are composited (e.g. splitting an LED strip).
        """
        pair = self._build_effect(name, level, options)
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

    def __repr__(self) -> str:
        parts = []
        for key, effects in self._effects.items():
            names = ", ".join(r.name for r, _ in effects)
            parts.append(f"{key}: [{names}]")
        return "\n".join(parts) if parts else "(no active effects)"
