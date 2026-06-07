# Context: aura-prototype

## Glossary

### Effect
A descriptor class in `effects/effect.py` that declares what capabilities an effect has. Constructor: `Effect(name, pixels=None, audio=None, vibration=None)`. `EffectManager` inspects each capability field each tick: `pixels is None` → no pixel buffer allocated, no render pass; `audio`/`vibration` are passed to outputs via `handle_event`. Builders return plain `Effect` instances — subclassing is only appropriate when there is genuine logic to add. All element effects live in `packs/effects/elements/`; registered under pack namespaces via an `EffectBuilder`.
_Avoid_: `renders_pixels` (removed — use `effect.pixels is not None`); calling `effect.update()` or `effect.render()` directly; defining an `Effect` subclass solely to hold a name

### EffectPixels
An abstract base class in `effects/effect.py` that owns pixel simulation and rendering for an effect. Exposes `update(elapsed: float)` and `render(output: PixelBuffer)`. `EffectManager` calls these directly — the `Effect` shell is not involved. Concrete subclasses: `LayerRenderer` (single layer + palette), `AddColorsRenderer` (multiple layer/palette pairs, additive color blend), `AddSamplesRenderer` (multiple layers, summed samples through one palette). None of the concrete subclasses carry a `name` field — identity lives on the `Effect` wrapper. An effect with `pixels is None` produces no pixel output — no buffer is allocated and no render pass runs.
_Avoid_: calling `update`/`render` on the `Effect` instance (these methods are removed from `Effect`); adding `name` to a compositor (name belongs on `Effect`)

### EffectAudio
A capability object in `effects/effect.py` that declares the audio behaviour of an effect. Holds `clips: dict[str, AudioPlaybackConfig]` — a map from event verb to playback config. Set on `Effect.audio`; if `None`, the effect produces no audio. `AudioEffectOutput` reads `effect.audio.clips.get(event.verb)` in `handle_event` to decide whether and how to play a sound.
_Avoid_: including `"stop"` as a clips key (the stop lifecycle verb does not trigger playback — teardown is handled by `flush()`)

### AudioPlaybackConfig
A value object in `effects/effect.py` declaring how a single audio clip should play. Fields: `name: str` (the clip name looked up in `AudioRegistry`) and `loop: bool` (`True` → voice 0, looping background; `False` → voice 1, one-shot). Additional playback fields (volume, fade, etc.) are deferred.

### EffectVibration
A placeholder capability object in `effects/effect.py` for future vibration hardware support. Holds `patterns: dict[str, object]` — a map from event verb to an opaque vibration config (type unspecified). Set on `Effect.vibration`; no hardware output implements it yet.

### EffectConfig
Runtime configuration passed to effect builders at construction. Three fields: `resolution` (sample detail, independent of pixel count — clamped to minimum `1`), `options` (effect-specific parameters as a plain dict, e.g. `{"level": 5}`), and `listeners` (notification callbacks invoked by name when significant rendering events occur).

### Layer
A composable simulation unit used by `EffectPixels` subclasses. Base class in `effects/layers/layer.py` defines `update(elapsed)` and `sample(position, pixel_count) -> float`. Concrete implementations: `ScrollLayer`, `FlameLayer`, `DriftNoiseLayer`, `SparkleLayer`, `ShapeLayer`. The compositors `LayerRenderer`, `AddColorsRenderer`, and `AddSamplesRenderer` combine layers into pixel output.
_Avoid_: importing layer helpers from anywhere other than `effects.layers`

### GameRule
An event handler registered with `GameEngine`. **Game-data-stateless** — a rule instance must not accumulate mutable game data as instance attributes. All data that changes over the life of a game (scores, durations, counters, health, inventory) must be stored and retrieved via the `GameState` accessor methods (`get`, `set`, `pop`, `delete`, `has`). Construction-time configuration (event maps, hardware callbacks, injected dependencies) is the only permitted use of instance attributes — rules register event handlers in `__init__` via `self.on()` and need not call `super().__init__()`.

### GameState
The game context passed to every rule handler each tick. Created by `GameEngine.create_state()` and owned by the caller. `GameEngine` never holds a reference between ticks. Exposes `effect_controls`, `network_controls`, `scene_controls`, read-only `elapsed`/`total`, and `queue_event(event)`. Mutable game data is stored and retrieved via `get(key, default)`, `set(key, value)`, `pop(key, type)`, `delete(key)`, `has(key)`. `clear_queue()` is for `SceneManager` during scene transitions only — rules must not call it.

### Timer
Owned internally by `GameEngine`. Tracks elapsed time per tick and cumulative total. Rules never hold a `Timer` reference — they access time only via `state.elapsed` and `state.total`. An optional `Timer` can be injected into `GameEngine` at construction for test-time clock control.

### Scene
A declarative bundle of a self-contained game context: `rules` (direct `GameRule` instances), `effect_packs` and `rule_packs` (name + min-version pairs validated at load time), optional `initial_data` seeding the `GameState` internal store, and optional lifecycle callbacks (`on_load`, `on_unload`, `on_suspend`, `on_resume`) each receiving only `effect_controls`. Carries no mutable runtime state — game data lives in the `GameState` that `SceneManager` creates on the scene's behalf.

### NetworkControls
Abstract base class (raises `NotImplementedError`) for network transmit. Exposes `send_ir(data: bytes)` and `send_radio(data: bytes)`. Always present on `GameState` as `state.network_controls` — the base class raises on any call; the live implementation is injected at construction time via `GameEngine`. Stored on `GameEngine` alongside `effect_controls` (hardware capability, shared across all scenes). The receive side is covered by `NetworkEvents.IRReceived` and `NetworkEvents.RadioReceived`.

### SceneControls
Abstract base class (raises `NotImplementedError`) with three methods: `load(name)`, `overlay(name)`, `pop()`. All three record a pending transition rather than acting immediately — `SceneManager` applies it after `engine.update(state)` completes (end-of-tick). `GameState.scene_controls` is always a `SceneControls` instance; the default raises on any call. `SceneManager` injects itself as the live implementation.

### SceneManager
Owns the scene stack and drives scene transitions. Wraps `GameEngine`; implements `SceneControls`. `load(name)` clears the stack and loads a fresh scene. `overlay(name)` suspends the active scene and pushes a new one. `pop()` unloads the top scene and resumes the previous one. `pop()` and `overlay()` raise `ValueError` if the stack has fewer entries than required.

### Scope
Identifies what a game effect targets — which outputs and players should display or respond to it. Each scope is output-agnostic — a scope routes to all outputs (LED, audio, vibration) registered for it; the outputs decide how to respond. Leaf scopes: `PERSONAL` (local player's device only), `DIRECTIONAL` (the direction indicator), `Global.MAIN` (primary shared effect area), `Global.BUFF` (positive status area), `Global.DEBUFF` (negative status area), `AMBIENT` (long-running background effects — loops, mood lighting, atmosphere). Composite scopes: `Global.ALL` (all three global zones), `NON_AMBIENT` (all scopes except AMBIENT — use for active gameplay effects), `Scope.ALL` (every scope including AMBIENT — use for teardown). `ScopeValue` is the Python type name — an implementation artifact caused by CircuitPython's lack of enum support. Use "scope" in domain language.
_Avoid_: ScopeValue (as a domain term); using AMBIENT to mean idle effect (AMBIENT is a routing scope, not a synonym for idle)

### EffectOutput
A hardware or software output registered with the effect system. Serves one or more scopes and receives rendered frames each tick. `receives_pixels: bool = True` — non-pixel outputs (audio, vibration) set this to `False`; `EffectManager` skips buffer allocation and render calls for them. Core methods: `update_pixels(scope_key, buffers, receipts)` (pixel outputs, once per scope key per tick), `flush()` (all outputs, once per tick — pixel outputs flush hardware; non-pixel outputs poll state), `clear_pixels(scope_key)` (go-dark signal), `handle_event(event: EffectEvent, scope_keys: frozenset[str], effect: Effect, receipt: EffectReceipt)` (effect lifecycle and verb events).
_Avoid_: output (ambiguous in multi-output contexts)

### EffectEvent
A structured event payload routed to every `EffectOutput.handle_event` in scope. Lives in `engine/events.py`. Three fields: `pack`, `name`, `verb`. Lifecycle verbs `"start"` and `"stop"` are emitted automatically by `EffectManager`. Custom verbs (e.g. `"peak"`, `"strike"`) are emitted when an effect calls `config.notify_listeners(verb)`.
_Avoid_: confusing with `Event` (game-rule events); assuming only `"start"`/`"stop"` verbs are possible

### Resolution
The mathematical detail level at which an effect generates its animation data. Independent of pixel count — an effect can be generated at resolution 20 and rendered into a 10-pixel buffer, which may look noticeably better than generating at resolution 10. Each `EffectOutput` declares a `min_resolution` — the minimum detail level it requires. The effect engine uses the highest `min_resolution` across all outputs an effect targets when constructing the effect. Pixel count (the number of LEDs written per tick) is a separate hardware concern controlled by the size of the buffer the output allocates.
_Avoid_: conflating resolution with pixel count

### EffectReceipt
A handle returned when an effect is started. `stop()` marks the receipt as stopped — `EffectManager` removes the effect at the top of the next tick. `is_stopped() -> bool` lets any holder test whether the effect has ended. Deferred cleanup is reentrance-safe. Carries two mutable output-control floats: `brightness` (visual scaling, 0.0–1.0) and `loudness` (audio scaling, 0.0–1.0), both defaulting to 1.0. Both are initialized from `options["brightness"]` and `options["loudness"]` respectively when the effect is started (defaulting to 1.0 if absent). Rules set these directly on a running receipt to vary intensity without restarting the effect. Each `EffectOutput` reads them independently — an output that ignores them renders at full intensity.
_Avoid_: using `options["brightness"]` as a runtime control mechanism (it only initializes the receipt; change `receipt.brightness` at runtime instead); setting `brightness` or `loudness` outside [0.0, 1.0] (clamping is the caller's responsibility)

### Idle effect
A low-level, looping effect running on a scope when no active game logic requires a specific response. Used to keep outputs visually active during standby or between triggered events. Replaced (via `set_effect`) when an active effect is started; restored when the active effect ends. Idle effects are optional — scopes may have no effect running at all.
_Avoid_: ambient effect, background effect (as synonyms for idle effect — `Scope.AMBIENT` is a routing destination, not a description of idle effects)

### AudioRegistry
A standalone registry in `engine/audio.py` that maps clip names (plain strings) to WAV file paths. Given to `AudioEffectOutput` at construction. Populated explicitly via `register(name, path)` calls — no naming-convention magic. `PackRegistry` may provide a helper to bulk-register a pack's `sounds/` directory, but `AudioRegistry` itself has no dependency on `PackRegistry`. The lookup key comes from `AudioPlaybackConfig.name` inside an `EffectAudio` clip map.
_Avoid_: using `PackRegistry.sound_path` for new audio effects (deprecated — migrate to `AudioRegistry`)

### AudioEffectOutput
A CircuitPython `EffectOutput` that drives `audiomixer.Mixer` via I2S. Registered on all scopes with `receives_pixels = False`. In `handle_event`, looks up `effect.audio.clips.get(event.verb)` to get an `AudioPlaybackConfig`, resolves the WAV path via `AudioRegistry`, and plays on voice 0 (`loop=True`) or voice 1 (`loop=False`). The `"stop"` verb does **not** halt audio — teardown for both voices is driven by `flush()` receipt guards. Rules trigger audio via `add_effect`/`set_effect` — they do not pass filenames. Audio-completion-driven effect lifecycle is a future opt-in.
_Avoid_: `PackRegistry.sound_path` for new effects (deprecated — use `AudioRegistry`); stopping playback in `handle_event` on `"stop"`

### Accelerometer
A hardware sensor (e.g. LIS3DH) that provides 3-axis acceleration readings (x, y, z) in m/s². Optional peripheral — absent when the hardware is not present. The engine treats it as an input source: readings are sampled each tick and packaged into `AccelerationData` carried by input events.
_Avoid_: IMU (overpromises — LIS3DH has no gyroscope or magnetometer)

### AccelerationData
A snapshot of 3-axis accelerometer readings (`x`, `y`, `z`) in m/s² at a point in time. Carried on `InputEvents.ButtonAndAcceleration` each tick. When no accelerometer is present, the field is `None` — it signals "no sensor data," not "device at rest." Rules that process acceleration must check for `None` before using the value.
_Avoid_: MovementData (imprecise — acceleration is always present, even when the device is stationary)
