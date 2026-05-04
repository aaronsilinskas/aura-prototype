import time

from effects.manager.manager import EffectManager
from effects.manager.scope import Scope, ScopeValue
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


effect_manager_hack = EffectManager() # Temporary global instance for testing until we have a better way to pass it to rules

class MakeEffectRule(GameRule):
    def handle_event(self, event: Event, state: GameState) -> None:
        if isinstance(event, InputEvents.ButtonAndMovement):
            # Process the button and movement data to determine the effect to trigger
            button_data = event.buttons
                        
            # Example logic to determine effect based on input
            if button_data.states["A"] == ButtonData.PRESSED:
                effect_manager_hack.set_effect(Scope.Global.ALL, "color.flash", {"duration": 3, "times": 2})
                

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
    
