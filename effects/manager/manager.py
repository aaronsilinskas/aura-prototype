from effects.effect import Effect, EffectState, EffectTimer
from effects.manager.scope import ScopeValue
from effects.palette import Palette
from effects.render import EffectRenderer, RendererConfig
from engine.timer import Timer

# TODO - level is really a specific option for spells, not a general option. Pull out to options dict?
# - need options dict for more general effects like flashes, etc
# TODO - manager will need to populate RendererConfig
# -- pixel_count and resolution will need to come from each driver, but re-use renderer if those
#   match
# -- listeners will need a hook to audio/vibration drivers to trigger
# TODO - need some kind of standard registry hook or file that will provide all available effects


class EffectBuilder:
    def __call__(self, name: str, config: RendererConfig, options: dict) -> EffectRenderer:
        """Build an EffectRenderer for the named effect.

        Args:
            name: The registered effect name (e.g. "color.flash").
            options: Configuration values for the effect's steps and shapes.
        """
        raise NotImplementedError


class EffectManager:
    __slots__ = ("_effects", "_timer")

    def __init__(self) -> None:
        # scope key -> list of active (EffectRenderer, EffectState) pairs
        self._effects: dict[str, list[tuple[EffectRenderer, EffectState]]] = {}
        self._timer: EffectTimer = EffectTimer()

    def _build_effect(self, name: str, options: dict) -> "tuple[EffectRenderer, EffectState]":
        """Construct an EffectRenderer paired with a fresh EffectState."""
        # TODO implement registry to build effect renderer(s) for drivers
        return EffectRenderer(Effect(name), Palette()), EffectState()

    def set_effect(self, scope: ScopeValue, name: str, options: dict) -> None:
        """Replace any running effect(s) in scope and start this one."""
        pair = self._build_effect(name, options)
        for key in scope.keys:
            self._effects[key] = [pair]

    def add_effect(self, scope: ScopeValue, name: str, options: dict) -> None:
        """Layer this effect alongside any running effects in scope.

        If nothing is running in scope, behaves like set_effect.
        The driver determines how layered effects are composited (e.g. splitting an LED strip).
        """
        pair = self._build_effect(name, options)
        for key in scope.keys:
            if key in self._effects:
                self._effects[key].append(pair)
            else:
                self._effects[key] = [pair]

    def stop_effect(self, scope: ScopeValue) -> None:
        """Stop all running effects in scope."""
        for key in scope.keys:
            if key in self._effects:
                del self._effects[key]

    def update(self, timer: Timer) -> None:
        """Tick all active effects in each scope."""
        self._timer.update(timer.elapsed)
        seen: set[int] = set()
        for effects in self._effects.values():
            for renderer, state in effects:
                renderer_id = id(renderer)
                if renderer_id not in seen:
                    seen.add(renderer_id)
                    renderer.update(state, self._timer)

    def __repr__(self) -> str:
        parts = []
        for key, effects in self._effects.items():  # TODO: expose effect name to fix r._effect.name
            names = ", ".join(r._effect.name for r, _ in effects)
            parts.append(f"{key}: [{names}]")
        return "\n".join(parts) if parts else "(no active effects)"
