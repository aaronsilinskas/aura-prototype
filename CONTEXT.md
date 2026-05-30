# Context: aura-prototype

## Glossary

### EffectRenderer
A base class in `effects/render.py` that subclasses override to drive all visual simulation state directly. Subclasses implement `name`, `update(timer)`, and `render(output)`. All ten element effects live in `packs/effects/elements/` and extend `EffectRenderer` using the layer helpers in `effects/layers/`. Registered under the `elements.*` namespace via `ElementBuilder`. Class attribute `renders_pixels: bool = True` — audio-only and vibration-only renderers set this to `False`; `EffectManager` skips pixel buffer allocation and `render()` calls for such renderers.
_Avoid_: "step-based effect", "prototype renderer" (the cutover is complete — all renderers use this direct approach)

### Layer
A composable simulation unit used by element `EffectRenderer` subclasses. The base class in `effects/layers/layer.py` defines `update(elapsed)` and `sample(position, pixel_count) -> float`. Concrete implementations: `ScrollLayer`, `FlameLayer`, `DriftNoiseLayer`, `SparkleLayer`, `ShapeLayer`. Layer-based renderers (`LayerRenderer`, `AddColorsRenderer`, `AddSamplesRenderer`) composite layers into pixel output.
_Avoid_: importing layer helpers from anywhere other than `effects.layers`

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
Identifies what a game effect targets — which outputs and players should display or respond to it. Each scope is output-agnostic — a scope routes to all outputs (LED, audio, vibration) registered for it; the outputs decide how to respond. Leaf scopes: `PERSONAL` (local player's device only), `DIRECTIONAL` (the direction indicator), `Global.MAIN` (primary shared effect area), `Global.BUFF` (positive status area), `Global.DEBUFF` (negative status area), `AMBIENT` (long-running background effects — loops, mood lighting, atmosphere). Composite scopes: `Global.ALL` (all three global zones), `NON_AMBIENT` (all scopes except AMBIENT — use for active gameplay effects), `Scope.ALL` (every scope including AMBIENT — use for teardown). `ScopeValue` is the Python type name — an implementation artifact caused by CircuitPython's lack of enum support. Use "scope" in domain language.
_Avoid_: ScopeValue (as a domain term); using AMBIENT to mean idle effect (AMBIENT is a routing scope, not a synonym for idle)

### EffectOutput
A hardware or software output registered with the effect system. Serves one or more scopes and receives rendered frames each tick. Translates pixel and event data into hardware calls (e.g. writing to an LED matrix or playing audio). Class attribute `receives_pixels: bool = True` — non-pixel outputs (audio, vibration) set this to `False`; `EffectManager` skips `create_buffer()`, `update_pixels()`, and `render()` for those outputs entirely, and does not pre-allocate frame buffers for them. Core methods: `update_pixels(scope_key, buffers, receipts)` (called once per registered scope key per tick — only when `receives_pixels = True`), `flush()` (called unconditionally once per output per tick — replaces `show_pixels()`; pixel outputs flush hardware, e.g. `strip.show()`; non-pixel outputs use this for per-tick polling such as checking playback state), `clear_pixels(scope_key)` (go-dark signal when the last effect on a scope stops), `handle_event(event: EffectEvent, scope_keys, receipt)` (react to effect lifecycle events emitted by `EffectManager`; receives a structured `EffectEvent` — never a raw string).
_Avoid_: output (ambiguous in multi-output contexts)

### EffectEvent
A structured effect lifecycle payload constructed by `EffectManager` when an effect starts or stops. Lives in `engine/events.py` alongside `Event` (game-rule events) — parallel concept, different subsystem. Holds three fields: `pack` (the pack name, e.g. `"rlgl"`), `name` (the bare effect name, e.g. `"red_light_music"`), and `verb` (`"start"` or `"stop"`). `EffectManager` constructs it directly for lifecycle events and passes it to `_notify_listeners`. `EffectOutput.handle_event` receives an `EffectEvent` — outputs never parse raw strings. Renderer-triggered signals (via `RendererConfig.notify_listeners`) are a separate path and do not produce `EffectEvent` objects.
_Avoid_: passing raw event name strings to `handle_event`; confusing with `Event` (game-rule events)

### Resolution
The mathematical detail level at which an effect generates its animation data. Independent of pixel count — an effect can be generated at resolution 20 and rendered into a 10-pixel buffer, which may look noticeably better than generating at resolution 10. Each `EffectOutput` declares a `min_resolution` — the minimum detail level it requires. The effect engine uses the highest `min_resolution` across all outputs an effect targets when constructing the renderer. Pixel count (the number of LEDs written per tick) is a separate hardware concern controlled by the size of the buffer the output allocates.
_Avoid_: conflating resolution with pixel count

### EffectReceipt
A handle returned when an effect is started. Callable from both rules and `EffectOutput` implementations. `stop()` marks the receipt as stopped — `EffectManager` removes the effect at the top of the next tick, firing a `"pack.effect.stop"` event. `is_stopped() -> bool` allows any holder to test whether the effect has ended (e.g. a rule checking if a sound is still playing, or `AudioEffectOutput` checking if a rule cancelled a sound). Deferred cleanup is reentrance-safe — calling `stop()` from within `EffectOutput.update()` takes effect on the next tick.
_Avoid_: `stop_effect_by_receipt` (removed — use `receipt.stop()` instead)

### Idle effect
A low-level, looping effect running on a scope when no active game logic requires a specific response. Used to keep outputs visually active during standby or between triggered events. Replaced (via `set_effect`) when an active effect is started; restored when the active effect ends. Idle effects are optional — scopes may have no effect running at all.
_Avoid_: ambient effect, background effect (as synonyms for idle effect — `Scope.AMBIENT` is a routing destination, not a description of idle effects)

### AudioEffectOutput
A hardware-only (`EffectOutput`) implementation that drives CircuitPython `audiomixer.Mixer` and `audiobusio.I2SOut`. Registered on **all scopes** with `receives_pixels = False` — so it receives `handle_event` calls for every effect on every scope without incurring any pixel buffer allocation. Uses `voice_count=2`: voice selection is determined by the event's `scope_keys` — if `"ambient"` is present → voice 0 (`loop=True`, background); otherwise → voice 1 (one-shot, replaces any current one-shot). In `handle_event` on `.verb == "start"`: resolves the sound file via `PackRegistry.sound_path(event.pack, event.name)` (maps to `<pack_source>/sounds/<effect>.wav`); silently ignores missing files; stores the receipt as `_loop_receipt` (voice 0) or `_once_receipt` (voice 1). In `handle_event` on `.verb == "stop"`: if receipt matches `_loop_receipt`, stops voice 0 and clears `_loop_receipt`. Voice 1 teardown is handled entirely in `flush()` — not in `handle_event`. In `flush()`: monitors `voice[1].playing` — when False, calls `_once_receipt.stop()` and clears it (signals `EffectManager` to remove the entry next tick); checks `_once_receipt.is_stopped()` as a symmetric guard to stop voice 1 early if a rule stopped the receipt before it finished naturally; checks `_loop_receipt.is_stopped()` as a defensive guard to stop voice 0 if a rule stopped the receipt directly. Rules trigger audio via standard `add_effect`/`set_effect` calls — they do not pass filenames or know which output handles the effect. Compound audio (loop + one-shot from a single effect instance) is not supported in this design — deferred to a future PRD.
_Avoid_: `AudioControls`, `AudioManager`, `AudioReceipt` (superseded by effects-based approach); `audio.loop`/`audio.once` generic pack (superseded by named per-game audio effects in game-specific effect packs)

### Accelerometer
A hardware sensor (e.g. LIS3DH) that provides 3-axis acceleration readings (x, y, z) in m/s². Optional peripheral — absent when the hardware is not present. The engine treats it as an input source: readings are sampled each tick and packaged into `AccelerationData` carried by input events.
_Avoid_: IMU (overpromises — LIS3DH has no gyroscope or magnetometer)

### AccelerationData
A snapshot of 3-axis accelerometer readings (`x`, `y`, `z`) in m/s² at a point in time. Carried on `InputEvents.ButtonAndAcceleration` each tick. When no accelerometer is present, the field is `None` — it signals "no sensor data," not "device at rest." Rules that process acceleration must check for `None` before using the value.
_Avoid_: MovementData (imprecise — acceleration is always present, even when the device is stationary)
