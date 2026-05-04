# Aura Prototype

A monorepo to prototype Aura Game Engine core features.


# Implementation Notes

*New New*
- Scene will specify rules, effects, palettes, etc
- Scenes can nest - pause could run as a parent to suspend child rules temporarily
- Finish effect manager registry, which will be populated by Scene
- Add Scene which takes rules, effects, and palettes so far
- SceneManager will layer on top of (overlay or hide) or replace Scenes. Rules can change Scenes

- Event = an event that will be processed by the game
- Message = from another device (IR, radio, BLE, Wifi). Has sender, receivers optional. Device IDs should be managed outside of game engine

- Sound can use file name to determine play once, loop, random select. Eg lightning_strike.wav (once), water_start_loop.wav, earth_shift_1/2/3.wav (random select)
- Vibration could have text files with sequences 

*New General Flow*

- Input \ network activity -> data objects -> wrapped in events like InputEvent
- events go into GameEngine for processing, which runs GameRules 
- GameRules alter game state and can call an effect shim to make effects
- These effects will be wired to also trigger sound and vibrations inside the effect shim
  - A new effect event design will be needed to standardize named events from effects
- RGB strips, sound, and vibration modules will consume the updated effect to render RGB strips, play sounds if defined, or play vibrations.

- use EffectManager.start/end_effect(slot/area, name, options, merge=true/false)
  - need to know published options (could just be documented, not programmatic and updated with version updates - all effects should have a default for no options)
  - slot/area/focus would be "player", "directional", etc
  - merge would be whether existing effects running in a slot/area/focus will be replaced
- make a single object that takes all parameters into a GameRule
  - engine (to load packs)
  - state (game state)
  - effect manager (trigger effects)

## Terms (Old - need an update)
Game Thing - the main game loop, holds game state, processes events with rules, then sends
  to listeners.
  Owns: Player, Team, Game State, Game Manager (scanning for games, joining/rejoining, creating)
Rules Thing - processes GameEvents with game rules, updates game state, can generate new
  GameEvents.
  Owns: Aura and other objects (potentially shared by rules) inserted into the game world
Listeners - receives GameEvents to trigger effects and other outputs.
  Owns: RGB, SFX, IR transmitter, radio transmitter drivers
Driver - lower level hardware interface.
OutputDriver - drivers for output like IR transmitter, RGB, SFX, etc.
  Drivers are used by Listeners. *Note: may not need this abstraction level, build later if
  needed*.
InputDriver - drivers that gather input and generate InputEvents
  *Always read IMU and generate events, no need for complex config in rules.*
  *Merge all inputs into a single event before sending to Game. This way multiple button
   and movements can be handled more efficiently.*
NetworkDriver - driver for network communications (IR, Radio, WiFi, etc)
InputEvent - event caused by physical input of some kind, e.g. button press, movement, etc.
GameEvent - processed by Rules to update game state. After processing, GameEvents are sent to
  Listeners.
Rule - a single rule that handles events and updates game state. Rules can be shared across
  games, and can be enabled/disabled by Rule Packs.
  Note: Rules with are versioned and signed by an author. Some rules will be official. Rule
  signatures should be verified by each device before being applied.
Rule Pack - a collection of rules that can be applied to a game, e.g. lobby rules, free for all
  rules, team deathmatch rules, etc. Rule Packs can be applied to a game when it's created.
  Note: Rule packs will list the version of each rule so older games are not broken by updates.
  Player join - verify that they have all required rules at the correct version

## Order of Operations
All event processing needs to be sequential: game thing -> rules thing -> listeners
  This is to ensure that Game Thing can ignore or modify events, then rules thing can,
  and listeners only see processed/filtered events.
Flow: (InputEvent | NetworkEvent) -> Game -> (GameEvent) -> Rules <> Game -> (GameEvent) -> Listeners

## Examples
Note: try to focus on minimal memory usage for events.

- Radio request to join game received:
Test Rule Pack
- Player pushes A or B button, generates a configured game event like "indicate color" or
  "cast spell"
- Additional rules to test SFX, IR, RGB, etc drivers.
Red Rover Game Rule Pack
- Player moves IMU when green or loses
- Player stops moving IMU when red or loses
- Player gets points for correct movement
- Player loses game after too many incorrect movements
- Start flashing when indicator will change soon
- Speed of change increases with each correct movement.
- Advanced mode -> direction matters, not just movement.
Fishing Game Rule Pack
- Player casts fishing line with button A or B
- Player gets bite with flashing light and SFX
- Player reels in with button, letting go if flashes red
- Add IMU to reeling for more fun
- Player catches fish, gets points, and can cast again
- Player loses fish, gets no points, and can cast again
Lobby Rule Pack
- Player selects a rule pack and starts a game
- Player joins a game, receives list of Rule Packs and versions, verifies that they have them,
  then sends join request with player name and list of Rule Packs and versions.
- Player device restart and rejoin game attempt.
Free For All Rule Pack
- Player creates new team (may not be allowed in some games)
- Player casts spell over IR
- Spell Hit IR packet received