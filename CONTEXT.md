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
A value object declaring how a single audio clip should play. Fields: `name` (clip name in `AudioRegistry`), `loop` (`True` → looping background; `False` → one-shot), and `stops_effect` (`False` default; `True` → when this one-shot finishes naturally, the owning `EffectReceipt` is stopped, ending the whole effect — pixels/vibration included — not just the sound). `stops_effect` describes the *effect's* end, distinct from the audio always stopping when it finishes; it generalizes the audio-only auto-stop to effects that also render. Combining `stops_effect=True` with `loop=True` is a contradiction (a loop never finishes) and is rejected at construction with `ValueError`.
_Avoid_: `stop_on_finish`, `end_effect`/`ends_effect` (the receipt vocabulary is `stop`, and `stops_effect` names the subject); reading `stops_effect` as "the sound stops" (the sound always stops on finish — this stops the effect)

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
The game context passed to every rule handler each tick. Exposes `effect_controls`, `network_controls`, `scene_controls`, read-only `elapsed`/`total`, and `queue_event`. Mutable game data stored via `get`/`get_or_none`/`set`/`pop`/`delete`/`has`. `get_or_none(key, expected_class)` returns `None` if absent, else validates with `expected_class` like `pop`.
_Avoid_: calling `clear_queue()` from rules (reserved for `SceneManager` during scene transitions); `get(key, None)` (use `get_or_none` instead)

### Phase
A named stage of a scene's game flow (Tag's Ready/Starting/Playing/Game Over; an RLGL Round's red/green sub-stages; a hardware_test mode). Identified by a `PhaseKey`.
_Avoid_: "state" (collides with `GameState`); "mode" except as the hardware_test label for a phase

### PhaseKey
An opaque, identity-typed constant naming one phase, defined once per scene in its `phases.py`. Compared by identity, so a bare string literal never matches it — a typo fails loudly instead of silently working.
_Avoid_: bare `str`/`int` phase values; comparing a phase against a string literal

### PhaseMachine
The mutable per-scene object cached in `GameState` that holds **only** the current `PhaseKey`, the once-per-entry flag, and the phase-start time. Holds no receipts. Reached through a scene's typed accessor (e.g. `tag_phase`), which owns the key and initial phase.
_Avoid_: storing receipts or per-phase scratch on it; auto-stopping effects inside `enter()`

### PhaseRule
A `GameRule` that owns one phase's lifecycle: `on_enter`, `on_exit`, phase-gated typed handlers (registered with the ordinary `self.on(EventType, handler)`, auto-gated to its phase), and `transition_to`. Exactly one per `(machine, phase)` — enforced at scene load.
_Avoid_: `take_just_entered()` or hand-rolled entry flags (use `on_enter`); a per-tick `on_event` hook (use ordinary `self.on` handlers); reaching `super().on(...)` directly (bypasses the phase guard)

### InPhaseRule
A `GameRule` whose typed handlers fire only while a given phase is active, with no lifecycle hooks and no transitions. The home for reactors that are merely active during a phase (e.g. Tag's hit detection). Any number may share a phase.
_Avoid_: making it own or change phases (use `PhaseRule`)

### Scene Config
A scene's tunable knobs (phase durations, thresholds, counts) resolved **once** into a single immutable object: built from the flat values a scene seeds via `scene.json` `initial_data`, with defaults applied at construction. Exposes derived calculations (e.g. level-scaled durations) as methods rather than as free functions that re-read state. One per scene (`RlglConfig`, `TagConfig`), cached in `GameState` under a single key. Concrete classes live in the scene's `rules/helpers/`.
_Avoid_: confusing with `EffectConfig` (effect-render config: resolution/options/listeners — unrelated to game tuning); spreading the same default across a `_DEFAULT_*` constant table and many `state.get(key, default)` read sites (the default belongs in the Config, defined once); re-reading and re-defaulting these values every tick (build once, cache)

### Timer
Owned internally by `GameEngine`. Rules access time only via `state.elapsed` and `state.total` — never hold a `Timer` reference.

### Scene
A declarative bundle of a self-contained game context: effect/rule packs, optional initial data, a `version` field (parsed from `scene.json` at discovery time), and references to its scene-local effects/rules. Carries no mutable runtime state — game data lives in a `GameState` that `SceneManager` creates on the scene's behalf, and the mutating import cache for scene-local items lives on the registry held by the persistent scene entry, never on the `Scene`.

### Scene-local effect / Scene-local rule
An effect or rule discovered from an optional `effects/` or `rules/` subdirectory inside a scene's own folder (the directory holding `scene.json`), loaded automatically when that scene loads and private to it — no other scene can reference it. Unlike a shared **Effect pack** / rule pack under `packs/`, it has no `version.txt` and no semver contract. Scene-local effects are addressed from rule code with the reserved `scene.` prefix (e.g. `set_effect(scope, "scene.victory_flash", …)`), which always resolves against the currently active scene's local effects.
_Avoid_: "private pack" (it is not a pack — no version, no pack-name layer); putting scene-only code under `packs/effects` or `packs/rules` (those are for shared, versioned, cross-scene building blocks)

### SceneLocalRegistry
A single-namespace registry for one scene's local effects (or rules): maps item name → module, exposing the same `get(item_name, expected_class)` / `items()` surface as `PackRegistry` so resolution is uniform, but with no version concept. Built once at scene discovery and held by the scene's persistent entry; shares its item-loading internals with `PackRegistry`.
_Avoid_: modelling scene-local items as a synthetic single `PackRegistry` pack (no version layer applies)

### NetworkControls
Abstract interface for network transmit (`send_ir`, `send_radio`). Always present on `GameState`; raises unless the live implementation is injected. The receive side is covered by `NetworkEvents`.

### SceneRegistry
Auto-discovers JSON-described scenes from a directory tree. Constructed with no arguments, then populated via `scan_dir(path, module_prefix)` (reads every subdirectory that contains a `scene.json`, and any optional `effects/` / `rules/` subdirs within it as that scene's scene-local items; `module_prefix` is the dotted import root for those local items). Provides `get(name) -> Scene` (fresh instance per call), `names() -> list[str]` (sorted), and `register(name, factory)` (in-memory escape hatch for tests). Validates required fields and version format at scan time so misconfigured scenes fail at startup. Calling `scan_dir` twice with the same path is a no-op; different paths that resolve the same scene name raise `ValueError`.
_Avoid_: registering scenes via `SceneManager` (it no longer accepts `register()`); constructing `SceneRegistry` after harness startup (scan once, then pass to `SceneManager`)

### SceneControls
Abstract interface with `load`, `overlay`, and `pop` — each records a pending transition applied after the current tick ends. `SceneManager` is the live implementation.

### SceneManager
Owns the scene stack and drives transitions. Constructed with `SceneManager(engine, effect_registry, rule_registry, scene_registry)` — no `register()` method; all scene lookup delegates to the injected `SceneRegistry`. `load` clears the stack; `overlay` suspends the active scene and pushes a new one; `pop` unloads the top and restores the previous. Every scene it unloads or suspends has its effects stopped on `Scope.ALL` automatically. On each transition it also pushes the now-active scene's scene-local effects to the effect controls (via a `set_local_effects` call reserved for `SceneManager`, like `clear_queue`), so the reserved `scene.` prefix resolves against the top-of-stack scene.
_Avoid_: calling `register()` on `SceneManager` (method removed — add scenes to `SceneRegistry` before construction)

### Scope
Identifies what a game effect targets. Output-agnostic — routes to all outputs (LED, audio, vibration) registered for it. Leaf scopes: `PERSONAL`, `DIRECTIONAL`, `Global.MAIN`, `Global.BUFF`, `Global.DEBUFF`, `AMBIENT`. Composite scopes: `Global.ALL` (all global zones), `NON_AMBIENT` (all except AMBIENT), `Scope.ALL` (every scope including AMBIENT — use for teardown).
_Avoid_: `ScopeValue` (implementation artifact); using `AMBIENT` to mean idle effect (`AMBIENT` is a routing scope, not a synonym for idle)

### EffectOutput
A hardware or software output registered with the effect system. `receives_pixels = False` for non-pixel outputs (audio, vibration) — `EffectManager` skips buffer allocation and render calls. Core methods: `update_pixels` (pixel outputs), `flush` (all outputs, once per tick), `clear_pixels`, `handle_event`.
_Avoid_: "output" (ambiguous in multi-output contexts)

### EffectEvent
A structured event payload routed to every `EffectOutput.handle_event` in scope. Three fields: `pack`, `name`, `verb`. Lifecycle verbs `"start"` and `"stop"` are emitted automatically; custom verbs (e.g. `"peak"`, `"strike"`) are emitted via `config.notify_listeners`.
_Avoid_: confusing with `Event` (game-rule events); assuming only `"start"`/`"stop"` verbs are possible

### EffectResolver
Maps a qualified effect name to its `EffectBuilder`, owning the reserved `scene.` prefix rule: a `scene.`-prefixed name resolves against the active scene's scene-local effects, any other `pack.`-prefixed name against the shared effect packs. Held by `EffectManager`, which delegates all effect-name resolution to it.
_Avoid_: putting qualified-effect-name parsing or the `scene.` rule in `EffectManager`; confusing with `EffectManager` (routing and rendering, not name resolution)

### Resolution
The mathematical detail level at which an effect generates animation data. Independent of pixel count. Each `EffectOutput` declares a `min_resolution`; the engine uses the highest across all targeted outputs.
_Avoid_: conflating resolution with pixel count

### EffectReceipt
A handle returned when an effect is started. `stop()` marks it stopped — `EffectManager` removes the effect next tick. Carries `brightness` (visual scaling, 0.0–1.0) and `loudness` (audio scaling, 0.0–1.0), both defaulting to 1.0. Rules set these directly on a running receipt to vary intensity without restarting.
_Avoid_: using `options["brightness"]` as a runtime control (it only initializes the receipt — change `receipt.brightness` at runtime); setting values outside [0.0, 1.0]

### Idle effect
A low-level, looping effect running on a scope when no active game logic requires a specific response. Replaced when an active effect starts; restored when it ends.
_Avoid_: "ambient effect", "background effect" as synonyms (`Scope.AMBIENT` is a routing destination, not a description of idle effects)

### Progress bar
A linear fill effect (`basic.progress`) that lights pixels from the first toward the last in proportion to a `progress` value in `[0.0, 1.0]`: `0.0` all dark, `1.0` all lit in a single `color` (default white), `0.5` the first half lit. The lit/dark boundary pixel is anti-aliased — lit in proportion to its coverage. `progress` is a build-time effect option, not a runtime control: changing it means re-issuing `set_effect`.
_Avoid_: confusing `progress` (0.0–1.0 spatial fill) with `Game Level` (1–10 player progression integer) or with receipt `brightness` (0.0–1.0 output-level visual scaling of the whole strip); treating `progress` as a runtime-mutable receipt field

### Effect Level
A 1–10 integer `level` option controlling an effect's visual/audio intensity. A build-time effect parameter, not a game concept.
_Avoid_: using `level` as a runtime control (it only initializes the effect); conflating with `Game Level`

### Game Level
A player's progression through a game session, stored in `GameState`. Integer in `[1, max_level]`: starts at 1, advances one per surviving Round, resets to 1 on game over or win. Drives difficulty scaling and the `Scope.AMBIENT` progress bar. Completing the Round *at* `max_level` wins.
_Avoid_: confusing with `Effect Level`; holding it as rule instance state (must live in `GameState`)

### Round
One red→green cycle at a single Game Level (red warning → red → green warning → green). Surviving its green phase advances the Game Level, or wins if played at `max_level`. A full game is `max_level` Rounds.
_Avoid_: "phase" (a Round spans several phases); "level-up" (the celebratory beat *between* Rounds, not the Round)

### AudioRegistry
A registry that maps clip names to WAV file paths. Populated explicitly via `register(name, path)` — no naming-convention magic.
_Avoid_: using `PackRegistry.sound_path` for new audio effects (deprecated — migrate to `AudioRegistry`)

### AudioEffectOutput
A CircuitPython `EffectOutput` driving audio via I2S, and the live `VoiceSink` adapter. Owns the hardware: the I2S amp, the `audiomixer.Mixer`, the per-slot WAV sources, and the `max_volume` calibration constant. Holds no voice-slot bookkeeping — it delegates that to a `VoicePool`. `handle_event` resolves the clip path from `AudioRegistry`, then calls `pool.claim`; `flush` calls `pool.sweep`. Constructed with `num_voices` (required) for a flat pool of that size.
_Avoid_: `PackRegistry.sound_path` for new effects; stopping playback in `handle_event` on `"stop"`; assuming a fixed voice count or role-assigned slots; putting slot bookkeeping back in the output (it belongs in `VoicePool`)

### VoicePool
A hardware-agnostic owner of audio voice-slot bookkeeping (lives in `hardware/shared/`, imports no CircuitPython). Each voice is a pre-allocated `_Slot` record (`__slots__ = receipt, is_loop, stops_receipt, loudness, claim_seq`) — one object per voice, mutated in place, never reallocated — so `_free(slot)` is a single-object reset rather than a lockstep update across parallel lists. The pool tracks which `EffectReceipt` occupies each slot and claim ordering via a monotonic counter. Public surface: `claim(sink, path, loop, stops_receipt, receipt) -> int` (returns the slot played, or -1 when the clip is dropped or fails to load) and `sweep(sink)` (per-tick: frees naturally-finished and externally-stopped slots, applies loudness changes). Drives all hardware through a `VoiceSink` port. Slot selection is side-effect-free and teardown is deferred until after a successful load, so a clip that fails to load never evicts a live voice. Any voice plays any clip type; selection finds the first idle slot, else an eviction policy applies: a new loop evicts the oldest playing loop (or, if none, the oldest one-shot); a new one-shot evicts the oldest playing one-shot (or is silently dropped if all voices hold loops). "Oldest" is the lowest claim-counter value. When a voice is released — by eviction or by natural one-shot finish — the pool stops the receipt itself if the slot's `stops_receipt` is set; otherwise receipt lifecycle stays with rules. `stops_receipt` is flattened at the `AudioEffectOutput.handle_event` boundary as `audio_only or stops_effect` and passed to `claim` as a single policy bool — the pool itself knows neither "audio-only" nor "stops_effect", only whether to stop the receipt on release. Audio-only effects (`pixels is None and vibration is None`) opt in implicitly (their audio *is* the effect); any other effect opts in explicitly via `AudioPlaybackConfig.stops_effect`. Both release events stop the receipt, so a rule polling `receipt.is_stopped()` is guaranteed to terminate even if the driving clip is evicted rather than finishing (the effect lives exactly as long as its clip holds a voice). Externally-stopped receipts are freed without re-stopping (rules already did).
_Avoid_: importing `audiobusio` / `audiocore` / `audiomixer` here (all hardware lives behind `VoiceSink`); reading mixer state directly; selecting and tearing down a slot before the clip has loaded; reintroducing parallel per-slot lists (use the `_Slot` record so the free/claim invariant lives in one place)

### VoiceSink
The port through which `VoicePool` reaches audio hardware — a real seam with two adapters (the live CircuitPython mixer and a recording fake in tests). Methods: `open_source(path) -> source | None` (load a clip; `None` on missing or unreadable file), `play(slot, source, loop)`, `stop(slot)` (stop the voice and close that slot's source — the single hardware-teardown path), `set_loudness(slot, loudness)` (applies `max_volume` internally), `is_playing(slot) -> bool`. `AudioEffectOutput` is the live adapter.
_Avoid_: passing a pre-multiplied hardware level across this seam (pass `0..1` loudness; the sink owns `max_volume`); leaking receipts through the port (the pool owns receipt lifecycle)

### Drv2605EffectOutput
A CircuitPython `EffectOutput` driving a DRV2605L haptic motor. Registered on all scopes with `receives_pixels = False`. Translates `VibrationConfig` constants to DRV2605L waveforms via an internal mapping; clears remaining slots before each play. A new event always interrupts the current sequence. `flush()` cuts the sequence short if the active receipt is externally stopped. Constructed by `build_hardware` in `device_builder.py`.
_Avoid_: constructing with a `None` motor; subclassing for different haptic controllers (extract a base only when a second controller is needed); reading `receipt.loudness` (the DRV2605L has no volume control — intensity is baked into the waveform)

### aura-device.json
The single on-device file holding **all** hardware configuration: button pins, IR pins/emitters, the `pixels` topology (matrix or per-scope NeoPixel), accelerometer/haptics presence, and audio amp pins/voices/volume. The `pixels` key names the LED/pixel output topology — distinct from the sibling `audio` / `haptics` outputs — echoing `EffectOutput.receives_pixels`. Pin references are name **strings** (e.g. `"D9"`), resolved against `board` only in the device-only builder. Read once at boot with `json` + `open()` (portable to CircuitPython and MicroPython). A missing file falls back to `DEFAULT_DEVICE_CONFIG` (stock PropMaker matrix) with a console message. _(Design vocabulary — local PRD `device-config-from-json`, not yet implemented.)_
_Avoid_: `settings.toml` (removed — CircuitPython-only, unreadable on MicroPython); keying the pixel section `output` (audio/haptics are outputs too — use `pixels`); putting `board` pin objects in the file (it carries pin-name strings); folding scene selection in here (out of scope; a future convergence point)

### DeviceConfig
The validated value object produced by the pure `parse_device_config(mapping)` parser (in `hardware/shared/`, no `board` import, pytest-covered). Normalizes and validates an `aura-device.json` mapping; constructs no hardware. Raises `ValueError` naming the offending field on malformed config, including a scope key not in `set(Scope.ALL.keys)` (the single source of truth for leaf-scope keys) or an IR emitter key not in the `engine.network` emitter vocabulary (`line`/`cone`/`area_of_effect`). `__init__` + `__slots__`, no `dataclasses`.
_Avoid_: importing `board` into the parser (pin names stay strings here); constructing hardware in the parser (that is `device_builder`'s job); re-hardcoding the leaf-scope key list (derive from `Scope.ALL.keys`); accepting unknown scope/emitter keys (validate, PhaseKey-style fail-loud)

### device_builder
The device-only generic hardware builder (`hardware/circuitpython/device_builder.py`), replacing the board-specific `propmaker.py` `setup_*` grab-bag. `build_hardware(config, board, ir_encoder=None, ir_decoder=None) -> DeviceHardware` resolves pin names via `board`, constructs the configured outputs/buttons/accelerometer/haptics/audio/IR, and wraps the IR transmitters in `HardwareNetworkControls`. Device-only, verified via `deploy-watch`. Pin-name resolution failures raise a message naming the offending field and pin.
_Avoid_: the name `propmaker` (it builds whatever the config describes, not one fixed board); returning a bare tuple/dict (return `DeviceHardware`); putting config parsing/validation here (that lives in the pure parser)

### DeviceHardware
The named bundle `device_builder.build_hardware` returns, consumed by examples and the scene runtime. `__slots__`: `outputs` (`list[EffectOutput]`), `buttons`, `accelerometer` (or `None`), `network_controls` (a built `HardwareNetworkControls`), `ir_receiver` (or `None`, polled each tick). Raw IR transmitters are an internal detail wrapped before return — the runtime never handles them directly.
_Avoid_: exposing raw transmitters (use `network_controls`); a bare tuple/dict (it is a named seam); building network controls in the runtime instead (the builder owns that)

### NeoPixelEffectOutput
A CircuitPython `EffectOutput` driving one NeoPixel strip per `Scope` (the alternative to a single LED matrix). Config maps each scope key to `{ pin, count }`. Implements the same scope-keyed routing as `MatrixEffectOutput`; declares `min_resolution` as the largest strip `count` across its scopes (resolution stays independent of pixel count). _(Design vocabulary — local PRD `device-config-from-json`, not yet implemented.)_
_Avoid_: conflating per-strip `count` with `min_resolution` (count sizes the buffer; resolution is detail level); requiring every scope to be wired (a build may configure only some scopes)

### Accelerometer
A hardware sensor providing 3-axis acceleration readings (x, y, z) in m/s². Optional — absent when hardware is not present. Readings are packaged into `AccelerationData` carried by input events.
_Avoid_: "IMU" (overpromises — LIS3DH has no gyroscope or magnetometer)

### AccelerationData
A snapshot of 3-axis accelerometer readings at a point in time. When no accelerometer is present, the field is `None` — signals "no sensor data," not "device at rest." Rules must check for `None` before using the value.
_Avoid_: `MovementData`

### ButtonData
A snapshot of button states at a point in time. Each button maps to one of four constants: `UP`, `DOWN`, `PRESSED` (transitioned down this frame), `RELEASED` (transitioned up this frame). Convenience query methods (`is_pressed`, `is_down`, etc.) return `bool`; `is_down` returns `True` on both the `PRESSED` and `DOWN` frames ("currently contacting"). Unknown button names return `False`/`None` rather than raising.
_Avoid_: reading `_states` directly (use the query methods); assuming `is_down` excludes the `PRESSED` frame

### IR transport
The hardware-agnostic infrared send/receive subsystem (`hardware/shared/`, no `pulseio`), reached through `PulseReader`/`PulseWriter` ports with CircuitPython adapters — the same seam as `VoicePool`/`VoiceSink`. Moves opaque `bytes` with no game semantics: transmit via `NetworkControls.send_ir`, receive surfaced as `NetworkEvents.IRReceived`.
_Avoid_: importing `pulseio` into shared IR code; encoding spell fields in the transport (that belongs to a game-layer codec over the payload)

### Wire-frame codec
Encoder/decoder pair mapping an opaque payload `byte`(s) ↔ IR pulse durations, injected into the IR transport (transmitter + receiver), which is itself wire-frame-agnostic. Two coexist: the **Aura wire-frame** (internal) and the **Tag protocol** (external). A scene picks its wire-frame by injecting the matching codec.
_Avoid_: assuming a single global wire-frame; treating wire-frames as interchangeable across scenes with different hardware

### Aura wire-frame
Aura's internal IR wire-frame: header mark/space, MSB-first bits, CRC-8, lead-out terminator. Carries any-length payloads and is free to change since both ends are Aura devices. Used for all Aura-to-Aura features.
_Avoid_: using it where third-party interop is required (use the **Tag protocol**)

### Tag protocol
A fixed, external IR wire-frame ported verbatim from third-party tooling and **immutable** — its timings and bit layout are a compatibility contract with non-Aura tag hardware, with no CRC. Coexists with the Aura wire-frame, selected per-scene via the **Wire-frame codec**.
_Avoid_: adding a CRC, altering timings, or otherwise diverging from the external spec; folding it into the Aura wire-frame

### TagData
The game-layer payload of a tag shot — `team`, `player`, `damage` packed into one opaque byte by the tag game-layer codec and handed to the IR transport as bytes. Game fields live here, never in the wire-frame, which transmits the byte without interpreting it.
_Avoid_: reading tag fields off the wire-frame; conflating the data codec (`TagData` ↔ byte) with the wire-frame codec (byte ↔ pulses)

### IR emitter
A directed infrared transmit channel. Constants `LINE` (narrow line-of-sight), `CONE`, `AREA_OF_EFFECT` are the `send_ir` vocabulary, defined in `engine/network.py` (not the shared transport) and each mapped to its own `InfraredTransmitter` by `HardwareNetworkControls`. The caller must name the emitter; sending to an unwired one is a programming error.
_Avoid_: importing `magic.CastType` for IR emitters (the network seam owns these); a default emitter on `send_ir` (intent must be explicit)

### IR multi-receiver
Several IR receivers, each on its own data line, returning the packet with the lowest **error margin**. Improves *reception reliability only* — it does not yield hit direction.
_Avoid_: treating the array as a direction finder (abandoned in field testing); sharing one data line across receivers

### IR error margin
The worst-case pulse-timing deviation (µs) tolerated while still decoding a packet. Lower is better; the key the multi-receiver uses to pick the best receiver.
_Avoid_: conflating with **IR signal strength** (a normalized derivative, not the raw margin)

### IR signal strength
A normalized 0.0–1.0 quality metric derived from a packet's error margin (timing error ≤30% of threshold = full strength). A coarse proximity stand-in, inferred from timing accuracy — not measured power, and conveys no direction.
_Avoid_: calling it "RSSI" as if measured; using it to derive hit direction

### Deploy-watch
The `scripts/deploy_watch.py` host tool that deploys an example and captures the resulting serial run, for unattended workflows (e.g. hardware profilers capturing measured metrics). Sibling to `deploy.py`: deploy flashes; deploy-watch flashes *and* captures. Always deploys — deploying is what produces the **reload boundary** the capture anchors to.
_Avoid_: treating it as a read-only serial monitor (it overwrites `code.py` and reboots); a no-deploy "just watch" mode

### Reload boundary
The device's soft-reload after `code.py` is written — the line between the stale pre-reload run and the fresh run to capture. Found via the **start anchor**; everything before it is discarded so a **stop marker** can't match the previous run.
_Avoid_: assuming it coincides with the deploy finishing (it lags behind it); capturing without anchoring to it

### Start anchor
The known substring marking the **reload boundary** (CircuitPython's soft-reboot banner). Capture discards lines until it appears, then honors the **stop marker**; if it never arrives, the run fails rather than capture stale data.
_Avoid_: anchoring on the profiler's `__PROFILE` header (downstream content, not the reboot); proceeding silently when it is missing

### Stop marker
The substring that ends a capture, matched only on **post-anchor** output so it reflects the freshly deployed run. Plain substring, no regex.
_Avoid_: regex; matching against pre-anchor output (a stale-run false stop)
