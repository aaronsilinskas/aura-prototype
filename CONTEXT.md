# Context: aura-prototype

## Glossary

### Effect
A descriptor declaring what capabilities an effect has. `EffectManager` inspects each capability field each tick: `pixels is None` → no pixel buffer or render pass; `audio`/`vibration` are passed to outputs via `handle_event`. Builders return plain `Effect` instances — subclassing is only appropriate when there is genuine logic to add.
_Avoid_: `renders_pixels` (removed — use `effect.pixels is not None`); calling `effect.update()` or `effect.render()` directly; defining an `Effect` subclass solely to hold a name

### EffectPixels
An abstract base class that owns pixel simulation and rendering for an effect. Exposes `update(elapsed)` and `render(output)`. `EffectManager` calls these directly on `effect.pixels` — the `Effect` shell is not involved. An effect with `pixels is None` produces no pixel output.
_Avoid_: calling `update`/`render` on the `Effect` instance (these methods are removed); adding `name` to a compositor (name belongs on `Effect`)

### EffectAudio
A capability object declaring the audio behaviour of an effect. Holds `clips: dict[str, AudioPlaybackConfig]` — a map from event verb to playback config. Set on `Effect.audio`; if `None`, the effect produces no audio.
_Avoid_: including `"stop"` as a clips key (teardown is handled by `flush()`, not `handle_event`)

### AudioPlaybackConfig
A value object declaring how a single audio clip should play. Fields: `name` (clip name in `AudioRegistry`) and `loop` (`True` → looping background; `False` → one-shot).

### EffectVibration
A capability object declaring the vibration behaviour of an effect. Holds `patterns: dict[str, VibrationConfig]` — a map from event verb to playback config. Set on `Effect.vibration`; if `None`, the effect produces no vibration.
_Avoid_: using raw DRV2605L waveform IDs as pattern values (hardware IDs belong in `Drv2605EffectOutput`'s internal mapping, not in the effect descriptor)

### VibrationConfig
A value object declaring how a vibration sequence should play. Holds `sequence: list[int]` — an ordered list of abstract constants defined as class-level attributes. Effect constants: `STRONG_CLICK`, `SHARP_CLICK`, `SOFT_BUMP`, `DOUBLE_CLICK`, `TRIPLE_CLICK`, `STRONG_BUZZ`. Pause constants: `PAUSE_250`, `PAUSE_500`, `PAUSE_1000` (0.25s, 0.5s, 1.0s). Constants are deliberately offset from DRV2605L hardware IDs so any unmapped value raises at the output layer.
_Avoid_: using raw DRV2605L waveform IDs in a `VibrationConfig` sequence (use the named class constants instead)

### EffectConfig
Runtime configuration passed to effect builders at construction. Fields: `resolution` (sample detail, minimum 1), `options` (effect-specific parameters), `listeners` (callbacks invoked by name on significant rendering events).

### Layer
A composable simulation unit used by `EffectPixels` subclasses. Defines `update(elapsed)` and `sample(position, pixel_count) -> float`. Compositors combine layers into pixel output.
_Avoid_: importing layer helpers from anywhere other than `effects.layers`

### GameRule
An event handler registered with `GameEngine`. **Game-data-stateless** — must not accumulate mutable game data as instance attributes. All game data (scores, durations, counters) must be stored and retrieved via `GameState` accessor methods. Construction-time configuration is the only permitted use of instance attributes.

### GameState
The game context passed to every rule handler each tick. Exposes `effect_controls`, `network_controls`, `scene_controls`, read-only `elapsed`/`total`, and `queue_event`. Mutable game data stored via `get`/`set`/`pop`/`delete`/`has`.
_Avoid_: calling `clear_queue()` from rules (reserved for `SceneManager` during scene transitions)

### Timer
Owned internally by `GameEngine`. Rules access time only via `state.elapsed` and `state.total` — never hold a `Timer` reference.

### Scene
A declarative bundle of a self-contained game context: rules, effect/rule packs, optional initial data, and optional lifecycle callbacks. Carries no mutable runtime state — game data lives in a `GameState` that `SceneManager` creates on the scene's behalf.

### NetworkControls
Abstract interface for network transmit (`send_ir`, `send_radio`). Always present on `GameState`; raises unless the live implementation is injected. The receive side is covered by `NetworkEvents`.

### SceneControls
Abstract interface with `load`, `overlay`, and `pop` — each records a pending transition applied after the current tick ends. `SceneManager` is the live implementation.

### SceneManager
Owns the scene stack and drives transitions. `load` clears the stack; `overlay` suspends the active scene and pushes a new one; `pop` unloads the top and resumes the previous.

### Scope
Identifies what a game effect targets. Output-agnostic — routes to all outputs (LED, audio, vibration) registered for it. Leaf scopes: `PERSONAL`, `DIRECTIONAL`, `Global.MAIN`, `Global.BUFF`, `Global.DEBUFF`, `AMBIENT`. Composite scopes: `Global.ALL` (all global zones), `NON_AMBIENT` (all except AMBIENT), `Scope.ALL` (every scope including AMBIENT — use for teardown).
_Avoid_: `ScopeValue` (implementation artifact); using `AMBIENT` to mean idle effect (`AMBIENT` is a routing scope, not a synonym for idle)

### EffectOutput
A hardware or software output registered with the effect system. `receives_pixels = False` for non-pixel outputs (audio, vibration) — `EffectManager` skips buffer allocation and render calls. Core methods: `update_pixels` (pixel outputs), `flush` (all outputs, once per tick), `clear_pixels`, `handle_event`.
_Avoid_: "output" (ambiguous in multi-output contexts)

### EffectEvent
A structured event payload routed to every `EffectOutput.handle_event` in scope. Three fields: `pack`, `name`, `verb`. Lifecycle verbs `"start"` and `"stop"` are emitted automatically; custom verbs (e.g. `"peak"`, `"strike"`) are emitted via `config.notify_listeners`.
_Avoid_: confusing with `Event` (game-rule events); assuming only `"start"`/`"stop"` verbs are possible

### Resolution
The mathematical detail level at which an effect generates animation data. Independent of pixel count. Each `EffectOutput` declares a `min_resolution`; the engine uses the highest across all targeted outputs.
_Avoid_: conflating resolution with pixel count

### EffectReceipt
A handle returned when an effect is started. `stop()` marks it stopped — `EffectManager` removes the effect next tick. Carries `brightness` (visual scaling, 0.0–1.0) and `loudness` (audio scaling, 0.0–1.0), both defaulting to 1.0. Rules set these directly on a running receipt to vary intensity without restarting.
_Avoid_: using `options["brightness"]` as a runtime control (it only initializes the receipt — change `receipt.brightness` at runtime); setting values outside [0.0, 1.0]

### Idle effect
A low-level, looping effect running on a scope when no active game logic requires a specific response. Replaced when an active effect starts; restored when it ends.
_Avoid_: "ambient effect", "background effect" as synonyms (`Scope.AMBIENT` is a routing destination, not a description of idle effects)

### AudioRegistry
A registry that maps clip names to WAV file paths. Populated explicitly via `register(name, path)` — no naming-convention magic.
_Avoid_: using `PackRegistry.sound_path` for new audio effects (deprecated — migrate to `AudioRegistry`)

### AudioEffectOutput
A CircuitPython `EffectOutput` driving audio via I2S. Two voices: voice 0 for looping backgrounds, voice 1 for one-shot clips. Teardown for both voices is driven entirely by `flush()` receipt guards. Audio completion never stops an effect receipt.
_Avoid_: `PackRegistry.sound_path` for new effects; stopping playback in `handle_event` on `"stop"`

### Drv2605EffectOutput
A CircuitPython `EffectOutput` driving a DRV2605L haptic motor. Registered on all scopes with `receives_pixels = False`. Translates `VibrationConfig` constants to DRV2605L waveforms via an internal mapping; clears remaining slots before each play. A new event always interrupts the current sequence. `flush()` cuts the sequence short if the active receipt is externally stopped. Constructed via `setup_drv2605(i2c)` in `propmaker.py`.
_Avoid_: constructing with a `None` motor; subclassing for different haptic controllers (extract a base only when a second controller is needed); reading `receipt.loudness` (the DRV2605L has no volume control — intensity is baked into the waveform)

### Accelerometer
A hardware sensor providing 3-axis acceleration readings (x, y, z) in m/s². Optional — absent when hardware is not present. Readings are packaged into `AccelerationData` carried by input events.
_Avoid_: "IMU" (overpromises — LIS3DH has no gyroscope or magnetometer)

### AccelerationData
A snapshot of 3-axis accelerometer readings at a point in time. When no accelerometer is present, the field is `None` — signals "no sensor data," not "device at rest." Rules must check for `None` before using the value.
_Avoid_: `MovementData`
