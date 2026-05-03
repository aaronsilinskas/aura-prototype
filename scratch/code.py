import time

from effects.effect import Effect, EffectState, EffectTimer
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


try:
    from typing import Final
except ImportError:
    pass  # Not available on CircuitPython


class ScopeValue:
    """A typed scope value. Use constants from Scope — do not construct directly."""

    __slots__ = ("_value", "keys", "members")

    def __init__(self, value: str, members: "list[ScopeValue] | None" = None) -> None:
        self._value: str = value
        self.members: "list[ScopeValue]" = members if members is not None else [self]
        self.keys: "tuple[str, ...]" = tuple(k._value for k in self.members)

    def __repr__(self) -> str:
        return self._value


class Scope:
    """Routing constants that tell drivers where to display or play an effect.

    Use PERSONAL or DIRECTIONAL for single-player feedback.
    Use Scope.Global.* constants for shared, multi-player display areas.
    """

    class Global:
        """Effect is visible/audible to all players. Use zone constants to route to sub-areas."""        
        MAIN: "Final" = ScopeValue("global.main")     # primary effect area (e.g. active spell)
        BUFF: "Final" = ScopeValue("global.buff")      # positive status effects
        DEBUFF: "Final" = ScopeValue("global.debuff")  # negative status effects
        ALL: "Final" = ScopeValue("global.all", [MAIN, BUFF, DEBUFF])       # entire global area, no differentiation
    
    PERSONAL: "Final" = ScopeValue("personal")         # only the local player's device
    DIRECTIONAL: "Final" = ScopeValue("directional")   # the direction the player is pointing
    ALL: "Final" = ScopeValue("all", [PERSONAL, DIRECTIONAL] + Global.ALL.members)                    # every scope, including all global zones

class EffectManager:
    __slots__ = ("_stacks", "_timer")

    def __init__(self) -> None:
        # scope key -> stack of frames; each frame is a list of (EffectRenderer, EffectState) pairs
        self._stacks: "dict[str, list[list[tuple[EffectRenderer, EffectState]]]]" = {}
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
            stack = self._stacks.get(key)
            if stack:
                stack[-1] = [pair]
            else:
                self._stacks[key] = [[pair]]

    def add_effect(self, name: str, scope: ScopeValue, options: "dict | None" = None) -> None:
        """Layer this effect on top of any running effects in scope.

        If nothing is running in scope, behaves like set_effect.
        The driver determines how layered effects are composited (e.g. splitting an LED strip).
        """
        pair = self._build_effect(name, options)
        for key in scope.keys:
            stack = self._stacks.get(key)
            if stack:
                stack[-1].append(pair)
            else:
                self._stacks[key] = [[pair]]

    def push_effect(self, name: str, scope: ScopeValue, options: "dict | None" = None) -> None:
        """Pause running effects in scope and start this one on top of the stack.

        Call pop_effect to remove this effect and resume what was running before.
        """
        pair = self._build_effect(name, options)
        for key in scope.keys:
            if key not in self._stacks:
                self._stacks[key] = []
            self._stacks[key].append([pair])

    def pop_effect(self, scope: ScopeValue) -> None:
        """Remove the top effect from the stack in scope and resume the previous one."""
        for key in scope.keys:
            stack = self._stacks.get(key)
            if stack:
                stack.pop()
                if not stack:
                    del self._stacks[key]

    def stop_effect(self, scope: ScopeValue) -> None:
        """Stop all running effects in scope, including any layered effects."""
        for key in scope.keys:
            if key in self._stacks:
                del self._stacks[key]

    def update(self, timer: Timer) -> None:
        """Tick all active effects in the top frame of each scope."""
        self._timer.update(timer.elapsed)
        seen: "set[int]" = set()
        for stack in self._stacks.values():
            if stack:
                for renderer, state in stack[-1]:
                    renderer_id = id(renderer)
                    if renderer_id not in seen:
                        seen.add(renderer_id)
                        renderer.update(state, self._timer)

    def __repr__(self) -> str:
        parts = []
        for key, stack in self._stacks.items(): # TODO: expose effect name to fix r._effect.name
            frames = " | ".join("[" + ", ".join(r._effect.name for r, _ in frame) + "]" for frame in stack)
            parts.append(f"{key}: {frames}")
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
    
