# aura-prototype — Domain Language

The canonical code-facing vocabulary for the Aura animation and game-logic engine — one term per entry, with the words to avoid. Magic-system vocabulary (elements, auras, spells) lives in the aura-docs vault.

## Glossary

### Effect
A descriptor declaring what capabilities an effect has (pixels, audio, vibration). Builders return plain `Effect` instances — subclass only when there is genuine logic to add.
_Avoid_: `renders_pixels` (use `effect.pixels is not None`); calling `effect.update()`/`render()` directly; an `Effect` subclass that only holds a name

### EffectPixels
The unit that owns pixel simulation and rendering for an effect. An effect with `pixels is None` produces no pixel output.
_Avoid_: calling `update`/`render` on the `Effect` shell; adding `name` to a compositor (name belongs on `Effect`)

### EffectAudio
A capability object declaring an effect's audio behaviour, mapping event verbs to playback configs. `None` means the effect produces no audio.
_Avoid_: a `"stop"` clips key (teardown is handled by `flush()`, not `handle_event`)

### AudioPlaybackConfig
A value object declaring how one audio clip plays: which clip, whether it loops, and whether finishing it stops the whole owning effect (`stops_effect`). `stops_effect` names the *effect's* end, not the sound's (the sound always stops on finish); combining it with `loop=True` is rejected.
_Avoid_: `stop_on_finish`, `end_effect`/`ends_effect`; reading `stops_effect` as "the sound stops"

### EffectVibration
A capability object declaring an effect's vibration behaviour, mapping event verbs to vibration configs. `None` means no vibration.
_Avoid_: raw DRV2605L waveform IDs as pattern values (hardware IDs live in the output, not the descriptor)

### VibrationConfig
A value object holding an ordered sequence of abstract vibration constants — effect constants (`STRONG_CLICK`, `SHARP_CLICK`, …) and pause constants (`PAUSE_250`, …). Constants are deliberately offset from DRV2605L hardware IDs so any unmapped value raises at the output layer.
_Avoid_: raw DRV2605L waveform IDs in a sequence (use the named constants)

### EffectConfig
Runtime configuration passed to effect builders at construction: `resolution`, effect-specific `options`, and `listeners`.

### Effect pack
An `EffectBuilder` owning a named, versioned set of effects under `packs/effects/`. Shared and cross-scene; games compose multiple packs at startup.
_Avoid_: calling a scene-local effect set a "pack" (a pack is shared, versioned, and cross-scene)

### DynamicValue
`float | Callable[[], float]` — a value that may be constant or computed fresh each sample.

### EffectShapeFunc
`Callable[[float], float]` — maps a normalized position in `[0, 1]` to an output value.

### Layer
A composable simulation unit used by `EffectPixels` subclasses; compositors combine layers into pixel output.
_Avoid_: importing layer helpers from anywhere other than `effects.layers`

### GameRule
An event handler registered with `GameEngine`. **Game-data-stateless** — all game data lives in `GameState`, never as mutable instance attributes (construction-time config is the only permitted instance state).

### GameState
The game context passed to every rule handler each tick. Exposes the controls seams (`effect_controls`, `network_controls`, `scene_controls`), read-only `elapsed`/`total`, `queue_event`, and typed get/set accessors for mutable game data.
_Avoid_: `clear_queue()` from rules (reserved for `SceneManager`); `get(key, None)` (use `get_or_none`)

### Phase
A named stage of a scene's game flow (e.g. Tag's Ready/Starting/Playing/Game Over), identified by a `PhaseKey`.
_Avoid_: "state" (collides with `GameState`); "mode" except as the hardware_test label

### PhaseKey
An opaque, identity-typed constant naming one phase. Compared by identity, so a bare string literal never matches — a typo fails loudly instead of silently working.
_Avoid_: bare `str`/`int` phase values; comparing a phase against a string literal

### PhaseMachine
The mutable per-scene object holding **only** the current `PhaseKey`, the once-per-entry flag, and the phase-start time — no receipts. Reached through a scene's typed accessor (e.g. `tag_phase`).
_Avoid_: storing receipts or per-phase scratch on it; auto-stopping effects inside `enter()`

### PhaseRule
A `GameRule` owning one phase's lifecycle: `on_enter`/`on_exit`, phase-gated handlers, and `transition_to`. Exactly one per `(machine, phase)`, enforced at scene load.
_Avoid_: hand-rolled entry flags (use `on_enter`); a per-tick `on_event` hook (use `self.on`); reaching `super().on(...)` (bypasses the phase guard)

### InPhaseRule
A `GameRule` whose handlers fire only while a given phase is active, with no lifecycle hooks and no transitions (e.g. Tag's hit detection). Any number may share a phase.
_Avoid_: making it own or change phases (use `PhaseRule`)

### Scene Config
A scene's tunable knobs (durations, thresholds, counts) resolved **once** into a single immutable object, with defaults applied at construction and derived calculations exposed as methods. One per scene (`RlglConfig`, `TagConfig`), cached in `GameState`.
_Avoid_: confusing with `EffectConfig`; spreading one default across a constant table and many `state.get(key, default)` sites; re-reading and re-defaulting these values every tick (build once, cache)

### Timer
Owned internally by `GameEngine`. Rules access time only via `state.elapsed`/`state.total`, never by holding a `Timer` reference.

### Scene
A declarative bundle of a self-contained game context: effect/rule packs, optional initial data, a `version`, and references to its scene-local effects/rules. Carries no mutable runtime state — game data lives in a `GameState`.

### Scene-local effect / Scene-local rule
An effect or rule discovered from an `effects/` or `rules/` subdirectory inside a scene's own folder, loaded with that scene and private to it. Unlike a shared **Effect pack**, it has no version or semver contract; addressed from rule code with the reserved `scene.` prefix.
_Avoid_: "private pack" (no version, no pack-name layer); putting scene-only code under `packs/`

### SceneLocalRegistry
A single-namespace registry for one scene's local effects (or rules), exposing the same `get`/`items` surface as `PackRegistry` but with no version concept.
_Avoid_: modelling scene-local items as a synthetic single-pack `PackRegistry`

### NetworkControls
The **game-facing**, send-only network seam a rule holds via `GameState.network_controls` (`send_ir`, `send_radio`). Deliberately never gains per-tick lifecycle methods — the transmit pump lives on the separate `TransmitPump` face — so a rule author never sees transmit machinery. `send_ir` is fire-and-forget (returns `None`).
_Avoid_: putting `poll_transmits()` or any per-tick pump on `NetworkControls` (it reads as a player command — keep the seam send-only); calling `poll_transmits()` through a `NetworkControls`-typed handle (reach it via `TransmitPump`)

### TransmitPump
The **runtime-facing** counterpart to `NetworkControls`, declaring `poll_transmits()` — it completes in-flight IR writes, starts the oldest queued payload (FIFO, one per call), releases the transmit gate, and returns per-emitter busy state. `HardwareNetworkControls` implements both faces; the runtime polls it every tick as `transmit_pump`.
_Avoid_: naming the pump after the gate (`update_ir_gate`); a single aggregate busy bool (emitters need independent status); allocating a fresh return dict per call (reuse the pre-allocated one — no per-tick allocation); putting `TransmitPump` in the rule-facing engine module

### SceneRegistry
Auto-discovers JSON-described scenes from a directory tree, then serves `get(name)` (a fresh `Scene` per call), `names()`, and a test-only `register`. Validates required fields and version format at scan time so misconfigured scenes fail at startup.
_Avoid_: registering scenes via `SceneManager` (it no longer accepts `register()`); constructing after harness startup (scan once, then pass to `SceneManager`)

### SceneControls
The rule-facing scene-transition seam: `load`, `overlay`, `pop`, each recording a pending transition applied after the current tick. `SceneManager` is the live implementation.

### SceneManager
Owns the scene stack and drives transitions: `load` clears the stack, `overlay` suspends the active scene and pushes a new one, `pop` restores the previous. Every unloaded or suspended scene has its effects stopped on `Scope.ALL`, and each transition republishes the now-active scene's local effects so the `scene.` prefix resolves against the top of the stack. Holds an injected `EffectAdmin` handle and drives every local-effects push and merge-strategy reset/capture/apply through it — never through a stack entry's `state.effect_controls`.
_Avoid_: calling `register()` on it (removed — add scenes to `SceneRegistry`); routing scene-transition effect calls through `state.effect_controls` (use the injected `EffectAdmin`)

### EffectControls
The **rule-facing** effect seam a rule holds via `GameState.effect_controls`: `set_effect`, `add_effect`, `stop_effect`, `set_merge_strategy`. Deliberately sheds the scene-transition operations — those live on the separate `EffectAdmin` face — so a rule author never sees them.
_Avoid_: adding `set_local_effects` or the merge-strategy snapshot lifecycle back onto this interface (they belong on `EffectAdmin`)

### EffectAdmin
The **scene-transition-facing** counterpart to `EffectControls`, declaring `reset_merge_strategies`, `capture_merge_strategies`, `apply_merge_strategies`, and `set_local_effects`. `EffectManager` implements both faces (mirroring `NetworkControls`/`TransmitPump`); `SceneManager` holds an injected `EffectAdmin` handle and reaches it exclusively through that seam, never through `state.effect_controls`.
_Avoid_: calling any `EffectAdmin` method from a `GameRule`; putting `EffectAdmin` in the rule-facing `EffectControls` interface

### Scope
Identifies what a game effect targets, output-agnostically. Leaf scopes: `PERSONAL`, `DIRECTIONAL`, `Global.MAIN/BUFF/DEBUFF`, `AMBIENT`. Composite scopes: `Global.ALL`, `NON_AMBIENT`, `Scope.ALL` (everything — use for teardown).
_Avoid_: `ScopeValue` (implementation artifact); using `AMBIENT` to mean idle effect (it is a routing scope)

### EffectOutput
A hardware or software output registered with the effect system. `receives_pixels = False` for non-pixel outputs (audio, vibration), which skip buffer allocation and render.
_Avoid_: "output" (ambiguous in multi-output contexts); importing it from `engine.effects.manager` (import from `engine.effects.output`)

### EffectEvent
A structured event payload (`pack`, `name`, `verb`) routed to every in-scope `EffectOutput.handle_event`. `"start"`/`"stop"` verbs are emitted automatically; custom verbs (`"peak"`, `"strike"`) via `notify_listeners`.
_Avoid_: confusing with `Event` (game-rule events); assuming only `"start"`/`"stop"` verbs exist

### EffectResolver
Maps a qualified effect name to its `EffectBuilder`, owning the reserved `scene.` prefix rule (a `scene.`-name resolves against the active scene's local effects, any other against shared packs). Held by `EffectManager`.
_Avoid_: putting the `scene.` rule in `EffectManager`; confusing with `EffectManager` (routing/rendering, not name resolution)

### Merge strategy
The per-scope policy deciding how a scope's stack of layered effect buffers becomes shown pixels. Set per rule via `EffectControls.set_merge_strategy`, defaulting to **Split**, reset on scene load and preserved across an `overlay`/`pop`. Two ship: **Split** and **Additive**. The per-overlay snapshot used to restore the pre-overlay choice on `pop` rides in `SceneManager`'s own scene stack entry (`_SceneStackEntry.saved_merge`), not inside `EffectManager` — the scene stack and the snapshot stack are one, so desync is unrepresentable.
_Avoid_: making it a per-output or `aura-device.json` choice; holding merge state on the output; a global (non-per-scope) strategy; a separate snapshot stack inside `EffectManager` (the scene stack entry owns it)

### Split
The default **merge strategy**: divides a scope's region into N near-equal contiguous parts, one per layered effect (bottom-to-top), so effects render side-by-side. A single effect fills the whole region unchanged; surplus effects beyond the pixel count get zero-width parts and stay invisible until earlier ones fall away.
_Avoid_: downsampling a full-width render into each part (each effect renders directly at its part's size); "slice"/"partition"

### Additive
The opt-in **merge strategy**: composites all N layered buffers into the full region by per-channel additive blend clamped to 255, each scaled by its receipt brightness, so effects overlap rather than share space. N == 1 is identical to Split.
_Avoid_: confusing with `AddColorsRenderer` (blends one effect's layers at sample level; Additive blends rendered buffers across effects); "merge"/"blend"/"overlay"

### Resolution
The mathematical detail level at which an effect generates animation data — independent of pixel count. Each `EffectOutput` declares a `min_resolution`; the engine uses the highest across targeted outputs.
_Avoid_: conflating resolution with pixel count

### EffectReceipt
A handle returned when an effect starts. `stop()` marks it for removal next tick. Carries `brightness` and `loudness` (0.0–1.0, default 1.0) that rules set directly to vary intensity without restarting.
_Avoid_: using `options["brightness"]` as a runtime control (change `receipt.brightness`); values outside [0.0, 1.0]

### Idle effect
A low-level, looping effect on a scope when no active game logic requires a response. Replaced when an active effect starts; restored when it ends.
_Avoid_: "ambient effect"/"background effect" (`Scope.AMBIENT` is a routing destination, not a description of idle effects)

### Progress bar
A linear fill effect (`basic.progress`) lighting pixels from first toward last in proportion to a `progress` value in `[0.0, 1.0]`, with an anti-aliased boundary pixel. `progress` is a build-time option, not a runtime control.
_Avoid_: confusing `progress` with `Game Level` or receipt `brightness`; treating `progress` as runtime-mutable

### Effect Level
A 1–10 integer `level` option controlling an effect's visual/audio intensity. A build-time parameter, not a game concept.
_Avoid_: using `level` as a runtime control; conflating with `Game Level`

### Game Level
A player's progression through a game session, stored in `GameState`. Integer in `[1, max_level]`: starts at 1, advances one per surviving Round, resets on game over or win. Completing the Round at `max_level` wins.
_Avoid_: confusing with `Effect Level`; holding it as rule instance state

### Round
One red→green cycle at a single Game Level (red warning → red → green warning → green). Surviving its green phase advances the Game Level, or wins if at `max_level`. A full game is `max_level` Rounds.
_Avoid_: "phase" (a Round spans several); "level-up" (the celebratory beat between Rounds)

### AudioRegistry
Maps clip names to WAV file paths, populated explicitly via `register(name, path)` — no naming-convention magic.
_Avoid_: `PackRegistry.sound_path` for new audio effects (deprecated)

### AudioEffectOutput
A CircuitPython `EffectOutput` driving audio via I2S, and the live `VoiceSink` adapter. Owns the hardware (amp, mixer, WAV sources, `max_volume`) but delegates voice-slot bookkeeping to a `VoicePool`.
_Avoid_: `PackRegistry.sound_path` for new effects; stopping playback in `handle_event` on `"stop"`; assuming a fixed voice count or role-assigned slots; putting slot bookkeeping back in the output

### VoicePool
A hardware-agnostic owner of audio voice-slot bookkeeping (imports no CircuitPython), driving all hardware through a `VoiceSink` port. Tracks which `EffectReceipt` occupies each slot and claim ordering; `claim` plays a clip (evicting oldest-first when full), `sweep` frees finished/stopped slots each tick. On release it stops the receipt itself when the slot's `stops_receipt` policy is set, so an effect lives exactly as long as its clip holds a voice.
_Avoid_: importing `audiobusio`/`audiocore`/`audiomixer` here (hardware lives behind `VoiceSink`); selecting and tearing down a slot before the clip loads; parallel per-slot lists (use the `_Slot` record)

### VoiceSink
The port through which `VoicePool` reaches audio hardware, with two adapters (the live CircuitPython mixer and a recording test fake). Loads/plays/stops clips per slot and applies loudness, owning `max_volume` internally.
_Avoid_: passing a pre-multiplied hardware level across this seam (pass `0..1` loudness); leaking receipts through the port

### Drv2605EffectOutput
A CircuitPython `EffectOutput` driving a DRV2605L haptic motor on all scopes (`receives_pixels = False`). Translates `VibrationConfig` constants to DRV2605L waveforms; a new event interrupts the current sequence.
_Avoid_: constructing with a `None` motor; subclassing for different haptic controllers (extract a base only when a second is needed); reading `receipt.loudness` (the DRV2605L has no volume control)

### aura-device.json
The single on-device file holding **all** hardware configuration: buttons, IR pins/emitters, the `pixels` list, accelerometer/haptics presence, and audio. `pixels` is a **list** of pixel outputs (matrix and/or strips; at most one matrix). Pin references are name **strings**, resolved against `board` only in the device-only builder. A missing file falls back to `DEFAULT_DEVICE_CONFIG`. Also carries an optional top-level `"scene"` string — per-boot game selection, read separately and **not** part of `DeviceConfig`.
_Avoid_: `settings.toml` (removed — CircuitPython-only, unreadable on MicroPython); keying the pixel section `output`; putting `board` pin objects in the file; adding a `scene` field to `DeviceConfig`

### DeviceConfig
The validated value object produced by the pure `parse_device_config` parser (no `board` import, pytest-covered) — it validates and normalizes an `aura-device.json` mapping but constructs no hardware. Holds `pixels` as a list of matrix/strip configs and raises `ValueError` naming the offending field on malformed input.
_Avoid_: importing `board` into the parser; constructing hardware in the parser (that is `device_builder`'s job); re-hardcoding the leaf-scope key list (derive from `Scope.ALL.keys`); accepting unknown scope/emitter keys

### Composition layer (app/)
The top-level `app/` package, split along the board-free / device-only seam: `scene_composition.py` builds the engine/effect/scene machinery (board-free, CPython-testable) and `scene_runtime.py` wires it to real hardware and drives the per-tick loop. The one place allowed to import both engine runtime machinery and `hardware.*`.
_Avoid_: importing `hardware.*` from `engine/`, `effects/`, `magic/`, `packs/`; putting board-only code in `scene_composition.py`

### SceneRuntime / build_scene_runtime
`build_scene_runtime(hw, scene_name)` builds the registries, `EffectManager`, `GameEngine`, and `SceneManager`, resolves the scene (falling back to `DEFAULT_SCENE`), loads it, and returns a `SceneRuntime` bundle of `manager`, `effect_manager`, and `timer`. `run_scene` is its only caller.
_Avoid_: duplicating the wiring or scene-name fallback at a call site; reaching into `SceneRuntime` beyond its three named slots

### device_builder
The device-only generic hardware builder. `build_hardware(config, board, …)` resolves pin names, constructs the configured outputs/buttons/accelerometer/haptics/audio/IR, and wraps IR transmitters in `HardwareNetworkControls`. **Single-call**: it claims pins without deiniting, so a second call raises "pin in use." Pixels/audio/IR are config-gated, but the accelerometer and DRV2605 haptics attach by **physical presence**, probed regardless of config.
_Avoid_: returning a bare tuple/dict (return `DeviceHardware`); putting config parsing here (lives in the pure parser); calling it twice in one process; assuming a minimal config yields a minimal bundle

### DeviceHardware
The named `__slots__` bundle `build_hardware` returns — a pure data holder with no board logic, CPython-importable: `outputs`, `buttons`, `accelerometer`, `network_controls` (typed `NetworkControls`), `transmit_pump` (typed `TransmitPump`), `ir_receiver`. `network_controls` and `transmit_pump` are the *same* `HardwareNetworkControls` instance seen through its two faces.
_Avoid_: exposing raw transmitters (use `network_controls`); a bare tuple/dict; building network controls in the runtime (the builder owns that)

### NeoPixelEffectOutput
A CircuitPython `EffectOutput` driving **one** NeoPixel strip, subdivided into scope **segments** by pixel range (the strip analogue of the matrix's row bands). Several strips may declare the same scope; the engine drives them in sync. Per-output brightness is a hardware-init concern applied to the strip object at construction, not per frame.
_Avoid_: the old per-scope shape (one strip per `Scope`); conflating segment length with `min_resolution`; a brightness field on this output; overlapping segments on one strip

### Accelerometer
A hardware sensor providing 3-axis acceleration readings (x, y, z) in m/s². Optional — absent when hardware is not present.
_Avoid_: "IMU" (overpromises — LIS3DH has no gyroscope or magnetometer)

### AccelerationData
A snapshot of 3-axis accelerometer readings. When no accelerometer is present the field is `None` — signals "no sensor data," not "device at rest."
_Avoid_: `MovementData`

### ButtonData
A snapshot of button states, each one of `UP`, `DOWN`, `PRESSED` (down this frame), `RELEASED` (up this frame). Query methods (`is_pressed`, `is_down`, …) return `bool`; `is_down` is `True` on both `PRESSED` and `DOWN`.
_Avoid_: reading `_states` directly (use the query methods); assuming `is_down` excludes the `PRESSED` frame

### IR transport
The hardware-agnostic infrared send/receive subsystem (no `pulseio`), reached through `PulseReader`/`PulseWriter` ports with CircuitPython adapters. Moves opaque `bytes` with no game semantics.
_Avoid_: importing `pulseio` into shared IR code; encoding spell fields in the transport

### Wire-frame codec
An encoder/decoder pair mapping an opaque payload ↔ IR pulse durations, injected into the (wire-frame-agnostic) IR transport. Two coexist — the **Aura wire-frame** and the **Tag protocol** — selected per scene.
_Avoid_: assuming a single global wire-frame; treating wire-frames as interchangeable across scenes

### Aura wire-frame
Aura's internal IR wire-frame: header mark/space, MSB-first bits, CRC-8, lead-out terminator. Carries any-length payloads and is free to change since both ends are Aura devices.
_Avoid_: using it where third-party interop is required (use the **Tag protocol**)

### Tag protocol
A fixed, external IR wire-frame ported verbatim from third-party tooling and **immutable** — its timings and bit layout are a compatibility contract with non-Aura hardware, with no CRC.
_Avoid_: adding a CRC, altering timings, or otherwise diverging; folding it into the Aura wire-frame

### TagData
The game-layer payload of a tag shot — `team`, `player`, `damage` packed into one opaque byte by the tag codec and handed to the transport as bytes. Game fields live here, never in the wire-frame.
_Avoid_: reading tag fields off the wire-frame; conflating the data codec (`TagData` ↔ byte) with the wire-frame codec (byte ↔ pulses)

### IR emitter
A directed infrared transmit channel. Constants `LINE`, `CONE`, `AREA_OF_EFFECT` are the `send_ir` vocabulary, each mapped to its own `InfraredTransmitter`. The caller must name the emitter; sending to an unwired one is a programming error.
_Avoid_: importing `magic.CastType` for IR emitters; a default emitter on `send_ir`

### IR multi-receiver
Several IR receivers, each on its own data line, returning the packet with the lowest **error margin**. Improves reception reliability only — it does not yield hit direction.
_Avoid_: treating the array as a direction finder (abandoned in field testing); sharing one data line across receivers

### IR error margin
The worst-case pulse-timing deviation (µs) tolerated while still decoding a packet. Lower is better; the key the multi-receiver uses to pick the best receiver.
_Avoid_: conflating with **IR signal strength** (a normalized derivative, not the raw margin)

### IR signal strength
A normalized 0.0–1.0 quality metric derived from a packet's error margin. A coarse proximity stand-in inferred from timing accuracy — not measured power, and conveys no direction.
_Avoid_: calling it "RSSI" as if measured; using it to derive hit direction

### IR receive-path telemetry
Monotonic-since-boot counters at each stage of the receive path (reader, receiver, decoder), owned end-to-end by the receiver and surfaced as an `IrTelemetrySnapshot`; a drop between adjacent counters names the lossy stage. `telemetry_line()` returns a formatted line only when a counter changed; `reset_telemetry()` zeroes the counters and the change-gate baseline together.
_Avoid_: aggregating hit/gated counts in the scene; per-tick allocation in the no-pulse path; auto-resetting counters; `run_scene` holding telemetry state itself

### Self-echo
The IR pulses a device's own receiver captures from its own emitter while transmitting. Decodes as a CRC-valid packet carrying the firing device's own identity — a phantom self-hit if surfaced. Suppressed by the **IR transmit gate**, never by game rules.
_Avoid_: suppressing it in a scene (the old Tag `deafen_until`/`deafen_window` hack); telling self-echo from a real overlapping shot at the pulse level (indistinguishable — drop both)

### IR transmit gate
The shared coordination primitive (`IrTransmitGate`) that keeps a device from decoding its own **self-echo**: transmitters drive it (`begin_transmit`/`end_transmit`), the receiver reads it through one query, `should_discard()` — `True` while transmitting, then exactly once more on the falling edge. Neither side references the other, and the gate knows nothing of the pulse ports. Shared across every transmitter on the device, so each `InfraredTransmitter` owns its own arm/release timing.
_Avoid_: a second source of truth for "transmitting"; exposing it on `DeviceHardware`; a public `consume_flush` (fold it into `should_discard`); calling `should_discard()` more than once per tick per receiver; storing a transmitter's armed flag on the shared gate

### Drain-but-discard
The receiver's gated-receive contract: while the **IR transmit gate** signals emission, every available pulse is still drained from the reader (so `PulseIn` never overflows) but none is decoded, and any in-progress decode is reset. A real shot overlapping our emission is intentionally lost. Discarded pulses count toward `pulses_dropped_transmitting`.
_Avoid_: leaving pulses in the buffer to overflow (drain even when discarding); decoding during emission "to catch a real shot"; counting discarded pulses as `pulses_seen`

### Inter-frame gap
The idle period between two IR shots, delivered by `PulseIn` as a single over-long "space" pulse. A pulse longer than the longest valid pulse plus margin (≈6500 µs) is treated as a frame terminator: it abandons a stalled partial decode and returns the decoder to idle. The gap-detection recovery for overlapping/corrupt frames; needs no clock.
_Avoid_: trying to "re-arm" or salvage a pulse from an overlapping frame (recognise the gap and start the next frame clean)

### Deploy-watch
The `scripts/deploy_watch.py` host tool that deploys an example and captures the resulting serial run, for unattended workflows. Sibling to `deploy.py`: deploy flashes; deploy-watch flashes *and* captures.
_Avoid_: treating it as a read-only serial monitor (it overwrites `code.py` and reboots); a no-deploy "just watch" mode

### Reload boundary
The device's soft-reload after `code.py` is written — the line between the stale pre-reload run and the fresh run to capture. Found via the **start anchor**.
_Avoid_: assuming it coincides with the deploy finishing (it lags behind it); capturing without anchoring to it

### Start anchor
The known substring marking the **reload boundary** (CircuitPython's soft-reboot banner). Capture discards lines until it appears; if it never arrives, the run fails rather than capture stale data.
_Avoid_: anchoring on the profiler's `__PROFILE` header (downstream content); proceeding silently when it is missing

### Stop marker
The substring that ends a capture, matched only on **post-anchor** output so it reflects the freshly deployed run. Plain substring, no regex.
_Avoid_: regex; matching against pre-anchor output (a stale-run false stop)
