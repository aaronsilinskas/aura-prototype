import time

from effects.effect import Effect, EffectState, EffectTimer
from effects.manager.scope import Scope, ScopeValue
from effects.palette import Palette
from effects.render import EffectRenderer
from engine.engine import GameEngine, GameRule, GameState
from engine.events import Event
from engine.input import ButtonData, InputEvents, MovementData
from engine.timer import Timer
from rules.debug_pack.event_logger import EventLoggerRule


game_engine = GameEngine()
game_engine.add_rules(EventLoggerRule())

# --- Gather input into an event ---

test_button_data = ButtonData(
    states={
        "A": ButtonData.UP,
        "B": ButtonData.DOWN,
        "C": ButtonData.PRESSED,
        "D": ButtonData.RELEASED,
    }
)
test_movement_data = MovementData(x_accel=0.0, y_accel=9.8, z_accel=0.0)

# Trigger an input event
input_event = InputEvents.ButtonAndMovement(test_button_data, test_movement_data)


class EffectManager:
    __slots__ = ("_effects", "_timer")

    def __init__(self) -> None:
        # scope key -> list of active (EffectRenderer, EffectState) pairs
        self._effects: "dict[str, list[tuple[EffectRenderer, EffectState]]]" = {}
        self._timer: EffectTimer = EffectTimer()

    def _build_effect(self, name: str, options: "dict | None") -> "tuple[EffectRenderer, EffectState]":
        """Construct an EffectRenderer paired with a fresh EffectState.

        TODO: look up registered effect by name, apply options as step/shape config.
        TODO: resolve the correct Palette for this effect from the registry or options.
        """
        return EffectRenderer(Effect(name), Palette()), EffectState()

    def set_effect(self, name: str, scope: ScopeValue, options: "dict | None" = None) -> None:
        """Replace any running effect(s) in scope and start this one."""
        pair = self._build_effect(name, options)
        for key in scope.keys:
            self._effects[key] = [pair]

    def add_effect(self, name: str, scope: ScopeValue, options: "dict | None" = None) -> None:
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
        seen: "set[int]" = set()
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

effect_manager_hack = EffectManager() # Temporary global instance for testing until we have a better way to pass it to rules

class MakeEffectRule(GameRule):
    def handle_event(self, event: Event, state: GameState) -> None:
        if isinstance(event, InputEvents.ButtonAndMovement):
            # Process the button and movement data to determine the effect to trigger
            button_data = event.buttons
                        
            # Example logic to determine effect based on input
            if button_data.states["A"] == ButtonData.PRESSED:
                effect_manager_hack.set_effect("color.flash", Scope.Global.ALL, {"duration": 3})
                

# - TODO: EventManager and standard naming for effects and options with defaults
# - TODO: Use ANSI effect renderer to see visuals without hardware
# - TODO: Single container object to pass all params to rules (engine, state, effect manager, etc)
# - TODO: EffectManager.start/end_effect(slot/area/focus, name, options, merge=true/false)
# = TODO: Set target focus for effect (e.g. player, directional, global) with merge/replace
# Trigger visual, sound, and vibration effect that runs on update
# - TODO: New standardized effect event name design for sound/vibration triggers

timer = Timer()

for _ in range(10):
    timer.update()

    # TODO: poll IR receiver, buttons, accelerometer to input event
    
    game_engine.queue_event(input_event)
    
    game_engine.update(timer)
    
    time.sleep(0.1)
    
