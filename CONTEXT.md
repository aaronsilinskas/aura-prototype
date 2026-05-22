# Context: aura-prototype

## Glossary

### GameRule
An event handler registered with `GameEngine`. **Stateless** — a rule instance must not accumulate mutable game data as instance attributes. All data that changes over the life of a game (scores, durations, counters, health, inventory) must live in `GameState.data`. Construction-time configuration injected via `__init__` (event maps, callbacks) is the only permitted use of instance attributes.

### GameState
The persistent game context owned by `GameEngine`. Passed by reference to every rule handler on every tick. Exposes `effect_controls`, `data`, read-only `elapsed`/`total` time properties, and a `queue_event(event)` method. Rules have no reference to `GameEngine` — `queue_event` is the only engine operation available inside a rule handler. The `data` dict is the canonical store for all mutable game data shared across rules. Rules must not write to `elapsed` or `total`.

### Timer
Owned internally by `GameEngine`. Tracks elapsed time per tick and cumulative total. Rules never hold a `Timer` reference — they access time only via `state.elapsed` and `state.total`. An optional `Timer` can be injected into `GameEngine` at construction for test-time clock control.

### Scene
A declarative bundle of a self-contained game context: `rules` (direct `GameRule` instances), `effect_packs` and `rule_packs` (name + min-version pairs validated at load time), optional `initial_data` seeding `GameState.data`, and optional lifecycle callbacks (`on_load`, `on_unload`, `on_suspend`, `on_resume`) each receiving only `effect_controls`. Carries no mutable runtime state — game data lives in the `GameState` that `SceneManager` creates on the scene's behalf.

### SceneControls
Abstract base class (raises `NotImplementedError`) with three methods: `load(name)`, `overlay(name)`, `pop()`. All three record a pending transition rather than acting immediately — `SceneManager` applies it after `engine.update()` completes (end-of-tick). `GameState.scene_controls` is always a `SceneControls` instance; the default raises on any call. `SceneManager` injects itself as the live implementation.

### SceneManager
Owns the scene stack and drives scene transitions. Wraps `GameEngine`; its `update()` calls `engine.update()` then applies any pending transition. Implements `SceneControls`. `load(name)` clears the entire stack top-down (active scene `on_unload` first), then loads the named scene with a fresh `GameState`. `overlay(name)` suspends the active scene (rules swapped out) and loads a new scene on top. `pop()` unloads the top scene and restores the underlying scene's rules and state. `pop()` and `overlay()` raise `ValueError` immediately if the stack has fewer entries than required.
