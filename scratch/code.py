import time

from engine.engine import GameEngine
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



timer = Timer()

for _ in range(10):
    timer.update()

    # TODO: poll IR receiver, buttons, accelerometer to input event
    
    game_engine.queue_event(input_event)
    
    game_engine.update(timer)
    
    time.sleep(0.1)
    
# Examples
# Note: try to focus on minimal memory usage for events.
# - Radio request to join game received:
# Test Rule Pack
# - Player pushes A or B button, generates a configured game event like "indicate color" or
#   "cast spell"
# - Additional rules to test SFX, IR, RGB, etc drivers.
# Red Rover Game Rule Pack
# - Player moves IMU when green or loses
# - Player stops moving IMU when red or loses
# - Player gets points for correct movement
# - Player loses game after too many incorrect movements
# - Start flashing when indicator will change soon
# - Speed of change increases with each correct movement.
# - Advanced mode -> direction matters, not just movement.
# Fishing Game Rule Pack
# - Player casts fishing line with button A or B
# - Player gets bite with flashing light and SFX
# - Player reels in with button, letting go if flashes red
# - Add IMU to reeling for more fun
# - Player catches fish, gets points, and can cast again
# - Player loses fish, gets no points, and can cast again
# Lobby Rule Pack
# - Player selects a rule pack and starts a game
# - Player joins a game, receives list of Rule Packs and versions, verifies that they have them,
#   then sends join request with player name and list of Rule Packs and versions.
# - Player device restart and rejoin game attempt.
# Free For All Rule Pack
# - Player creates new team (may not be allowed in some games)
# - Player casts spell over IR
# - Spell Hit IR packet received