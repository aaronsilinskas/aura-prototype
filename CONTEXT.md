# Context: aura-prototype

## Glossary

### GameRule
An event handler registered with `GameEngine`. **Stateless** — a rule instance must not accumulate mutable game data as instance attributes. All data that changes over the life of a game (scores, durations, counters, health, inventory) must be stored and retrieved via the `GameState` accessor methods (`get`, `set`, `pop`, `delete`, `has`). Construction-time configuration injected via `__init__` (event maps, callbacks) is the only permitted use of instance attributes.

### GameState
The game context passed to every rule handler each tick. Created by `GameEngine.create_state()` and owned by the caller — `SceneManager` in scene-managed games, or the standalone loop otherwise. `GameEngine` never holds a reference to it between ticks. Exposes `effect_controls`, `network_controls`, `scene_controls`, read-only `elapsed`/`total` time properties, and `queue_event(event)`. Also exposes `clear_queue()` for use by `SceneManager` during scene transitions only — rules must not call it. Rules have no reference to `GameEngine` — `queue_event` is the only engine operation available inside a rule handler. Mutable game data shared across rules is accessed through five typed methods: `get(key, default)` (returns the stored value or default — default required), `set(key, value)` (stores a value), `pop(key, type)` (removes and returns a guaranteed-present value — validates with `isinstance` at runtime and raises `KeyError` if absent), `delete(key)` (removes a key silently — no-op if absent), and `has(key)` (tests whether a key is present). Rules must not write to `elapsed` or `total`.

### Timer
Owned internally by `GameEngine`. Tracks elapsed time per tick and cumulative total. Rules never hold a `Timer` reference — they access time only via `state.elapsed` and `state.total`. An optional `Timer` can be injected into `GameEngine` at construction for test-time clock control.

### Scene
A declarative bundle of a self-contained game context: `rules` (direct `GameRule` instances), `effect_packs` and `rule_packs` (name + min-version pairs validated at load time), optional `initial_data` seeding the `GameState` internal store, and optional lifecycle callbacks (`on_load`, `on_unload`, `on_suspend`, `on_resume`) each receiving only `effect_controls`. Carries no mutable runtime state — game data lives in the `GameState` that `SceneManager` creates on the scene's behalf.

### NetworkControls
Abstract base class (raises `NotImplementedError`) for network transmit. Exposes `send_ir(data: bytes)` and `send_radio(data: bytes)`. Always present on `GameState` as `state.network_controls` — the base class raises on any call; the live implementation is injected at construction time via `GameEngine`. Stored on `GameEngine` alongside `effect_controls` (hardware capability, shared across all scenes). The receive side is covered by `NetworkEvents.IRReceived` and `NetworkEvents.RadioReceived`.

### SceneControls
Abstract base class (raises `NotImplementedError`) with three methods: `load(name)`, `overlay(name)`, `pop()`. All three record a pending transition rather than acting immediately — `SceneManager` applies it after `engine.update(state)` completes (end-of-tick). `GameState.scene_controls` is always a `SceneControls` instance; the default raises on any call. `SceneManager` injects itself as the live implementation.

### SceneManager
Owns the scene stack and drives scene transitions. Wraps `GameEngine`; its `update()` calls `engine.update(state)` with the active scene's state, then applies any pending transition. Implements `SceneControls`. `load(name)` clears the entire stack top-down (active scene `on_unload` first), then loads the named scene with a fresh `GameState`. `overlay(name)` suspends the active scene (rules swapped out) and loads a new scene on top. `pop()` unloads the top scene, swaps the engine's rules via `set_rules()`, and resumes passing the restored `GameState` from the stack triple to `engine.update(state)`. `pop()` and `overlay()` raise `ValueError` immediately if the stack has fewer entries than required.

### Idle effect
A low-level, looping effect running on a scope when no active game logic requires a specific response. Used to keep outputs visually active during standby or between triggered events. Replaced (via `set_effect`) when an active effect is started; restored when the active effect ends.
_Avoid_: ambient effect, background effect
