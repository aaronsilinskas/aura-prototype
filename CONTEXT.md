# Context: aura-prototype

## Glossary

### Prototype Renderer
An `EffectRenderer` implementation that drives all visual simulation state directly, bypassing the `Effect`/`EffectStep`/`EffectState` pipeline. Prototype renderers are the intended production replacement for the step-based element effects — they are production-quality code being proven out before the old API is retired, not throwaway sketches. Each prototype is paired with a `*PrototypeBuilder` registered under the `elements.*_prototype` namespace so it can coexist with the step-based effect during the migration period. Cutover happens all-at-once across all ten elements once two gates are met: (1) a designer approves each element's look at all levels via side-by-side comparison on hardware (not strict parity — prototypes may intentionally improve on the old effect), and (2) performance benchmarks confirm a meaningful frame-time improvement (current estimate: 20–30% reduction). At cutover, each `*_prototype.py` is renamed to replace the corresponding step-based file and re-registered under the original `elements.*` name, and all helpers are promoted to the `effects` module — both happen in a single atomic PR. No changes to scenes or any other caller are required. The full cutover (helpers promotion, tests, rename, deletion) is tracked as #191 and must close before the cutover PR merges.
_Avoid_: "visual reference only", "throwaway prototype" (these are permanent)

### Layer (prototype helper)
The base class for all simulation layers used by prototype renderers. Lives in `packs/effects/elements/helpers/` for now — intentionally scoped to the `elements` pack during the prototype phase. Moves to the top-level `effects` module as part of the cutover tracked in #191.
_Avoid_: importing from `packs.effects.elements.helpers` outside the `elements` pack (use the `effects` module path once promoted)

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

### Scope
Identifies what a game effect targets — which outputs and players should display or respond to it. Leaf scopes: `PERSONAL` (local player's device only), `DIRECTIONAL` (the direction indicator), `Global.MAIN` (primary shared effect area), `Global.BUFF` (positive status area), `Global.DEBUFF` (negative status area). Composite scopes: `Global.ALL` (all three global zones), `Scope.ALL` (every scope). `ScopeValue` is the Python type name — an implementation artifact caused by CircuitPython's lack of enum support. Use "scope" in domain language.
_Avoid_: ScopeValue (as a domain term)

### EffectOutput
A hardware or software output registered with the effect system. Serves one or more scopes and receives rendered frames each tick. Translates pixel and event data into hardware calls (e.g. writing to an LED matrix or playing audio).
_Avoid_: output (ambiguous in multi-output contexts)

### Resolution
The mathematical detail level at which an effect generates its animation data. Independent of pixel count — an effect can be generated at resolution 20 and rendered into a 10-pixel buffer, which may look noticeably better than generating at resolution 10. Each `EffectOutput` declares a `min_resolution` — the minimum detail level it requires. The effect engine uses the highest `min_resolution` across all outputs an effect targets when constructing the renderer. Pixel count (the number of LEDs written per tick) is a separate hardware concern controlled by the size of the buffer the output allocates.
_Avoid_: conflating resolution with pixel count

### EffectReceipt
A handle returned when an effect is started. Used to stop that specific running effect by reference. Invalidated when the effect ends.

### Idle effect
A low-level, looping effect running on a scope when no active game logic requires a specific response. Used to keep outputs visually active during standby or between triggered events. Replaced (via `set_effect`) when an active effect is started; restored when the active effect ends. Idle effects are optional — scopes may have no effect running at all.
_Avoid_: ambient effect, background effect

### AudioEffectOutput
A hardware-only (`EffectOutput`) implementation that drives CircuitPython `audiomixer.Mixer` and `audiobusio.I2SOut`. Uses `voice_count=2`: voice 0 for looping background tracks, voice 1 for one-shot sound effects. Registered with `EffectManager` on `Scope.PERSONAL`. Rules trigger audio by calling `add_effect(Scope.PERSONAL, "audio.loop" | "audio.once", 1, {"file": "<name>"})` via `EffectControls`; `AudioEffectOutput.handle_event` receives the routed `"audio:loop:<name>"` / `"audio:once:<name>"` event and starts playback. Loop lifetime is tracked via `EffectReceipt` stored in `GameState` and stopped via `stop_effect_by_receipt`.
_Avoid_: `AudioControls`, `AudioManager`, `AudioReceipt` (superseded by effects-based approach)

### Accelerometer
A hardware sensor (e.g. LIS3DH) that provides 3-axis acceleration readings (x, y, z) in m/s². Optional peripheral — absent when the hardware is not present. The engine treats it as an input source: readings are sampled each tick and packaged into `AccelerationData` carried by input events.
_Avoid_: IMU (overpromises — LIS3DH has no gyroscope or magnetometer)

### AccelerationData
A snapshot of 3-axis accelerometer readings (`x`, `y`, `z`) in m/s² at a point in time. Carried on `InputEvents.ButtonAndAcceleration` each tick. When no accelerometer is present, the field is `None` — it signals "no sensor data," not "device at rest." Rules that process acceleration must check for `None` before using the value.
_Avoid_: MovementData (imprecise — acceleration is always present, even when the device is stationary)
