# aura-prototype — Domain Language

The canonical code-facing vocabulary for the Aura animation and game-logic engine — one term per entry, with the words to avoid. Magic-system vocabulary (elements, auras, spells) lives in the aura-docs vault.

## Glossary

### Effect
A descriptor declaring what capabilities an effect has (pixels, audio, haptic). Builders return plain `Effect` instances — subclass only when there is genuine logic to add.
_Avoid_: `renders_pixels` (use `effect.pixels is not None`); calling `update()`/`render()` directly; an `Effect` subclass that only holds a name

### EffectPixels
The capability that owns pixel simulation and rendering for an effect; `pixels is None` means no pixel output.
_Avoid_: calling `update`/`render` on the `Effect` shell; putting `name` on a compositor (it belongs on `Effect`)

### EffectAudio
A capability declaring an effect's audio behaviour, mapping event verbs to playback configs; `None` means no audio.
_Avoid_: a `"stop"` clips key (teardown is `flush()`, not `handle_event`)

### AudioPlaybackConfig
A value object for how one clip plays: which clip, whether it loops, and whether finishing it stops the whole owning effect (`stops_effect`).
_Avoid_: `stop_on_finish`, `end_effect`; reading `stops_effect` as "the sound stops" (it names the effect's end); combining it with `loop=True` (rejected)

### EffectHaptic
A capability declaring an effect's haptic behaviour, mapping event verbs to `HapticPattern`s; `None` means no haptic output.
_Avoid_: raw DRV2605L waveform IDs as values (hardware IDs live in the output); "vibration" (use `haptic`)

### HapticPattern
A value object holding an ordered sequence of abstract haptic constants — effect constants (`STRONG_CLICK`, …) and pause constants (`PAUSE_250`, …) — offset from hardware IDs so any unmapped value fails at the output.
_Avoid_: raw DRV2605L waveform IDs; `HapticConfig` (collides with the device-config `HapticsConfig`, which gates hardware presence — a different axis)

### EffectConfig
Runtime configuration passed to effect builders at construction: `resolution`, effect-specific `options`, and `listeners`.

### Effect pack
An `EffectBuilder` owning a named, versioned set of effects under `packs/effects/`; shared and cross-scene.
_Avoid_: calling a scene-local effect set a "pack" (a pack is shared, versioned, cross-scene)

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
The game context passed to every rule handler each tick: the controls seams (`effect_controls`, `network_controls`, `scene_controls`), read-only `elapsed`/`total`, `queue_event`, and typed get/set accessors for mutable game data.
_Avoid_: `clear_queue()` from rules (reserved for `SceneManager`); `get(key, None)` (use `get_or_none`)

### Phase
A named stage of a scene's game flow (e.g. Tag's Ready/Starting/Playing/Game Over), identified by a `PhaseKey`.
_Avoid_: "state" (collides with `GameState`); "mode" except as the hardware_test label

### PhaseKey
An opaque, identity-typed constant naming one phase; compared by identity, so a bare string literal never matches and a typo fails loudly.
_Avoid_: bare `str`/`int` phase values; comparing a phase against a string literal

### PhaseMachine
The mutable per-scene holder of the current `PhaseKey`, the once-per-entry flag, and the phase-start time; reached through a scene's `PhaseSlot`.
_Avoid_: storing receipts or per-phase scratch on it; auto-stopping effects inside `enter()`

### PhaseSlot
The single per-scene typed accessor owning a phase machine's `GameState` key and initial phase; every one of a scene's phase rules and its module-level phase reference share the *same* instance, so "same key ⇒ same `PhaseMachine`" holds by construction.
_Avoid_: constructing a fresh `PhaseSlot` per rule (import the scene's one); passing a raw machine-key string to a phase rule; confusing it with the generic `StateSlot`

### PhaseRule
A `GameRule` owning one phase's lifecycle: `on_enter`/`on_exit`, phase-gated handlers, and `transition_to`; exactly one per `(machine, phase)`.
_Avoid_: hand-rolled entry flags (use `on_enter`); reaching `super().on(...)` (bypasses the phase guard)

### InPhaseRule
A `GameRule` whose handlers fire only while a given phase is active, with no lifecycle hooks and no transitions; any number may share a phase.
_Avoid_: making it own or change phases (use `PhaseRule`)

### Scene Config
A scene's tunable knobs (durations, thresholds, counts) resolved **once** into a single immutable object, cached in `GameState`. One per scene (`RlglConfig`, `TagConfig`).
_Avoid_: confusing with `EffectConfig`; re-reading and re-defaulting these values every tick (build once, cache)

### Timer
Owned internally by `GameEngine`. Rules access time only via `state.elapsed`/`state.total`, never by holding a `Timer` reference.

### Scene
A declarative bundle of a self-contained game context: effect/rule packs, optional initial data, a `version`, and references to its scene-local effects/rules. Carries no mutable runtime state.

### Scene-local effect / Scene-local rule
An effect or rule loaded from an `effects/` or `rules/` subdirectory inside a scene's own folder, private to it and addressed with the reserved `scene.` prefix. Unlike an **Effect pack** it has no version.
_Avoid_: "private pack"; putting scene-only code under `packs/`

### SceneLocalRegistry
A single-namespace registry for one scene's local effects (or rules), with the same `get`/`items` surface as `PackRegistry` but no version concept.
_Avoid_: modelling scene-local items as a synthetic single-pack `PackRegistry`

### Registry lookup errors
The typed `ValueError` subclasses (`RegistryError` base; `UnknownPackError`, `UnknownItemError`, `MissingItemAttributeError`, `ItemTypeError`) that registries raise for lookup failures; `EffectResolver` dispatches on the exception **type**, so message wording stays a free display detail.
_Avoid_: classifying a registry failure by `str(exc)`/`startswith` on the message

### NetworkControls
The **game-facing**, send-only network seam a rule holds via `GameState.network_controls` (`send_ir`, `send_radio`); the transmit pump lives on the separate `TransmitPump` face.
_Avoid_: putting `poll_transmits()` or any per-tick pump on it (keep the seam send-only)

### TransmitPump
The **runtime-facing** counterpart to `NetworkControls`, declaring `poll_transmits()`, which the runtime polls every tick. `HardwareNetworkControls` implements both faces.
_Avoid_: naming the pump after the gate (`update_ir_gate`); allocating a fresh return dict per call; putting it in the rule-facing engine module

### SceneRegistry
Auto-discovers JSON-described scenes from a directory tree, then serves `get(name)` (a fresh `Scene` per call), `names()`, and a test-only `register`; validates required fields and version format at scan time.
_Avoid_: registering scenes via `SceneManager` (it no longer accepts `register()`); constructing after harness startup (scan once)

### SceneControls
The rule-facing scene-transition seam: `load`, `overlay`, `pop`, each recording a pending transition applied after the current tick. `SceneManager` is the live implementation.

### SceneManager
Owns the scene stack and drives transitions (`load` clears, `overlay` suspends and pushes, `pop` restores), stopping unloaded/suspended scenes' effects on `Scope.ALL` and republishing the active scene's local effects. Routes every local-effects push and merge-strategy admin through an injected `EffectAdmin`.
_Avoid_: calling `register()` on it (removed); routing scene-transition effect calls through `state.effect_controls` (use the injected `EffectAdmin`)

### EffectControls
The **rule-facing** effect seam a rule holds via `GameState.effect_controls`: `set_effect`, `add_effect`, `stop_effect`, `set_merge_strategy`; scene-transition operations live on `EffectAdmin`.
_Avoid_: adding `set_local_effects` or the merge-strategy snapshot lifecycle back onto it

### EffectAdmin
The **scene-transition-facing** counterpart to `EffectControls` (`reset_merge_strategies`, `capture_merge_strategies`, `apply_merge_strategies`, `set_local_effects`). `EffectManager` implements both faces; `SceneManager` reaches it only through this seam.
_Avoid_: calling any `EffectAdmin` method from a `GameRule`; putting it in the rule-facing `EffectControls`

### Scope
Identifies what a game effect targets, output-agnostically. Leaf scopes: `PERSONAL`, `DIRECTIONAL`, `Global.MAIN/BUFF/DEBUFF`, `AMBIENT`. Composite scopes: `Global.ALL`, `NON_AMBIENT`, `Scope.ALL` (everything — use for teardown).
_Avoid_: `ScopeValue` (implementation artifact); using `AMBIENT` to mean idle effect (it is a routing scope)

### EffectOutput
A hardware or software output registered with the effect system; `receives_pixels = False` for non-pixel outputs (audio, haptic), which skip buffer allocation and render.
_Avoid_: "output" (ambiguous in multi-output contexts); importing it from `engine.effects.manager` (import from `engine.effects.output`)

### EffectEvent
A structured event payload (`pack`, `name`, `verb`) routed to every in-scope `EffectOutput.handle_event`; `"start"`/`"stop"` are emitted automatically, custom verbs (`"peak"`, `"strike"`) via `notify_listeners`.
_Avoid_: confusing with `Event` (game-rule events); assuming only `"start"`/`"stop"` verbs exist

### EffectResolver
Maps a qualified effect name to its `EffectBuilder`, owning the reserved `scene.` prefix rule (a `scene.`-name resolves against the active scene's local effects, any other against shared packs). Held by `EffectManager`.
_Avoid_: putting the `scene.` rule in `EffectManager`; confusing with `EffectManager` (routing/rendering, not name resolution)

### Merge strategy
The per-scope policy deciding how a scope's stack of layered effect buffers becomes shown pixels; set per rule via `EffectControls.set_merge_strategy`, defaulting to **Split**. Two ship: **Split** and **Additive**.
_Avoid_: making it a per-output or `aura-device.json` choice; holding merge state on the output; a global (non-per-scope) strategy

### Split
The default **merge strategy**: divides a scope's region into N near-equal contiguous parts, one per layered effect (bottom-to-top), so effects render side-by-side. A single effect fills the whole region.
_Avoid_: downsampling a full-width render into each part; "slice"/"partition"

### Additive
The opt-in **merge strategy**: composites all N buffers into the full region by per-channel additive blend clamped to 255, each scaled by its receipt brightness, so effects overlap rather than share space.
_Avoid_: confusing with `AddColorsRenderer` (layer-level, one effect); "merge"/"blend"/"overlay"

### Resolution
The mathematical detail level at which an effect generates animation data, independent of pixel count; each `EffectOutput` declares a `min_resolution` and the engine uses the highest across targeted outputs.
_Avoid_: conflating resolution with pixel count

### EffectReceipt
A handle returned when an effect starts; `stop()` marks it for removal next tick. Carries `brightness` and `loudness` (validating, `[0.0, 1.0]`) that rules set directly to vary intensity without restarting.
_Avoid_: using `options["brightness"]` as a runtime control (change `receipt.brightness`); values outside `[0.0, 1.0]` (raises `ValueError`)

### Idle effect
A low-level, looping effect on a scope when no active game logic requires a response; replaced when an active effect starts, restored when it ends.
_Avoid_: "ambient effect"/"background effect" (`Scope.AMBIENT` is a routing destination, not a description of idle effects)

### Progress bar
A linear fill effect (`basic.progress`) lighting pixels from first toward last in proportion to a build-time `progress` value in `[0.0, 1.0]`, with an anti-aliased boundary pixel.
_Avoid_: confusing `progress` with `Game Level` or receipt `brightness`; treating `progress` as runtime-mutable

### Effect Level
A 1–10 integer `level` option controlling an effect's visual/audio intensity; a build-time parameter, not a game concept.
_Avoid_: using `level` as a runtime control; conflating with `Game Level`

### Game Level
A player's progression through a game session, stored in `GameState`; integer in `[1, max_level]`, starting at 1, advancing one per surviving Round, resetting on game over or win.
_Avoid_: confusing with `Effect Level`; holding it as rule instance state

### Round
One red→green cycle at a single Game Level (red warning → red → green warning → green); surviving its green phase advances the Game Level, or wins at `max_level`. A full game is `max_level` Rounds.
_Avoid_: "phase" (a Round spans several); "level-up" (the celebratory beat between Rounds)

### AudioRegistry
Maps clip names to WAV file paths, populated explicitly via `register(name, path)` — no naming-convention magic.
_Avoid_: `PackRegistry.sound_path` for new audio effects (deprecated)

### AudioEffectOutput
A CircuitPython `EffectOutput` driving audio via I2S and the live `VoiceSink` adapter; owns the hardware (amp, mixer, WAV sources) but delegates voice-slot bookkeeping to a `VoicePool`.
_Avoid_: stopping playback in `handle_event` on `"stop"`; assuming a fixed voice count or role-assigned slots; putting slot bookkeeping back in the output

### VoicePool
A hardware-agnostic owner of audio voice-slot bookkeeping (imports no CircuitPython), driving hardware through a `VoiceSink` port; `claim` plays a clip (evicting oldest-first when full), `sweep` frees finished/stopped slots each tick.
_Avoid_: importing CircuitPython audio libs here (hardware lives behind `VoiceSink`); parallel per-slot lists (use the `_Slot` record)

### VoiceSink
The port through which `VoicePool` reaches audio hardware (live CircuitPython mixer + a recording test fake); applies loudness and owns `max_volume`.
_Avoid_: passing a pre-multiplied hardware level across the seam (pass `0..1` loudness); leaking receipts through the port

### Drv2605EffectOutput
A CircuitPython `EffectOutput` driving a DRV2605L haptic driver on all scopes (`receives_pixels = False`); translates `HapticPattern` constants to waveforms, a new event interrupting the current sequence.
_Avoid_: constructing with a `None` driver; reading `receipt.loudness` (the DRV2605L has no volume control); "motor" for the injected instance (use `driver`)

### aura-device.json
The single **required** on-device file holding all hardware configuration; a missing file raises. Sections: `buttons`, `ir`, `pixels`, `audio`, `i2c`, `spi`, `radio`, `sdcard`, `accelerometer`, `haptics`, plus a top-level `"scene"` string (read separately, **not** part of `DeviceConfig`). `pixels` and `buttons` are each an optional, possibly-empty list.
_Avoid_: `settings.toml` (removed — unreadable on MicroPython); keying the pixel section `output`; putting `board` pin objects in the file; adding a `scene` field to `DeviceConfig`

### DeviceConfig
The validated value object produced by the pure `parse_device_config` parser (no `board` import) — it validates and normalizes an `aura-device.json` mapping but constructs no hardware. `isolate(keep)` derives a new config with every isolatable component but `keep` disabled.
_Avoid_: importing `board` into the parser; constructing hardware in the parser (that is `device_builder`'s job); hand-listing the isolatable components (derive from `__slots__`)

### Component enabled toggle
The optional `enabled` boolean on every hardware component config object (default `True`); `enabled: false` retains a parsed, fully-validated section but tells `device_builder` not to build it. `buttons` is a bare pin-name list and is not gated.
_Avoid_: treating `enabled: false` as omitting the section at parse time (validation still runs in full); assuming `i2c`/`spi` `enabled: false` falls back to default pins (each builds no bus at all); writing `.enabled` after parse (use `isolate`)

### Composition layer (app/)
The top-level `app/` package: `scene_composition.py` builds the engine/effect/scene machinery (board-free, CPython-testable) and `scene_runtime.py` wires it to real hardware and drives the per-tick loop. The one place allowed to import both engine runtime machinery and `hardware.*`.
_Avoid_: importing `hardware.*` from `engine/`, `effects/`, `magic/`, `packs/`; putting board-only code in `scene_composition.py`

### SceneRuntime / build_scene_runtime
`build_scene_runtime(hw, scene_name)` wires the registries, managers, and engine, resolves and loads the scene (raising when *scene_name* isn't registered), and returns a `SceneRuntime` bundle (`manager`, `effect_manager`, `timer`, `ir`, `radio`) that `run_scene`'s per-tick loop drives.
_Avoid_: duplicating the wiring or scene-name resolution at a call site; hand-sequencing `poll_transmits`/`receive` (drive `ir.update()`/`radio.update()`)

### device_builder
The device-only hardware builder: `build_hardware(config, board, …)` resolves pin names and constructs the configured outputs/buttons/sensors/IR/radio, wrapping transmitters and the radio transport in `HardwareNetworkControls`. Single-call (claims pins without deiniting); every component is config-gated, never presence-probed.
_Avoid_: returning a bare tuple/dict (return `DeviceHardware`); putting config parsing here (lives in the pure parser); calling it twice in one process

### DeviceHardware
The named `__slots__` bundle `build_hardware` returns — a board-free data holder: `outputs`, `buttons`, `accelerometer`, `network_controls`, `transmit_pump`, `ir_receiver`, `radio`. `network_controls` and `transmit_pump` are the *same* `HardwareNetworkControls` seen through two faces.
_Avoid_: exposing raw transmitters (use `network_controls`); a bare tuple/dict

### RadioTransport
The board-free half-duplex radio **port** `RadioManager` and `HardwareNetworkControls.send_radio` reach the chip through — one port for both directions because an RFM69-class chip is half-duplex. The live adapter is `Rfm69RadioTransport`.
_Avoid_: splitting it into send/receive ports; importing `adafruit_rfm69` here (that lives in the adapter)

### RadioManager
The board-free per-tick owner of the radio receive path; `update()` polls the transport once and exposes `received`. No transmit pump (the chip is half-duplex), and it builds the `NetworkEvents.RadioReceived` event itself.
_Avoid_: a transmit pump or pump-before-receive order; a value-returning `update()` (read `received`)

### Rfm69RadioTransport
The live CircuitPython `RadioTransport` adapter wrapping `adafruit_rfm69.RFM69` — the only module importing that library, via a deferred import so a config with no `radio` section never requires it installed.
_Avoid_: importing `adafruit_rfm69` anywhere else; reading the driver without checking `payload_ready` first (blocks)

### NeoPixelEffectOutput
A CircuitPython `EffectOutput` driving **one** NeoPixel strip, subdivided into scope **segments** by pixel range; several strips may share a scope and are driven in sync.
_Avoid_: the old per-scope shape (one strip per `Scope`); conflating segment length with `min_resolution`; a brightness field on this output; overlapping segments on one strip

### Accelerometer
A hardware sensor providing 3-axis acceleration readings (x, y, z) in m/s²; optional, absent when hardware is not present.
_Avoid_: "IMU" (the LIS3DH has no gyroscope or magnetometer)

### AccelerationData
A snapshot of 3-axis accelerometer readings; `None` when no accelerometer is present — signals "no sensor data," not "device at rest."
_Avoid_: `MovementData`

### ButtonData
A snapshot of button states, each one of `UP`, `DOWN`, `PRESSED` (down this frame), `RELEASED` (up this frame); query methods return `bool`, and `is_down` is `True` on both `PRESSED` and `DOWN`.
_Avoid_: reading `_states` directly (use the query methods); assuming `is_down` excludes the `PRESSED` frame

### IR transport
The hardware-agnostic infrared send/receive subsystem (no `pulseio`), reached through `PulseReader`/`PulseWriter` ports; moves opaque `bytes` with no game semantics.
_Avoid_: importing `pulseio` into shared IR code; encoding spell fields in the transport

### InfraredManager
The board-free per-tick owner of the IR sequence: `update()` runs the transmit pump **then** receive, owning the pump-before-receive order; results (`received`, `last_signal_strength`, `last_error_margin`, `telemetry_line()`) are read after the call. Does not build the game event.
_Avoid_: importing `NetworkEvents`/game-event vocabulary here (the event is built in `run_scene`); a value-returning `update()`; calling it a hardware "driver"

### Wire-frame codec
An encoder/decoder pair mapping an opaque payload ↔ IR pulse durations, injected into the IR transport; two coexist — the **Aura wire-frame** and the **Tag protocol** — selected per scene.
_Avoid_: assuming a single global wire-frame; treating wire-frames as interchangeable across scenes

### Aura wire-frame
Aura's internal IR wire-frame (header mark/space, MSB-first bits, CRC-8, lead-out terminator); carries any-length payloads and is free to change since both ends are Aura devices.
_Avoid_: using it where third-party interop is required (use the **Tag protocol**)

### Tag protocol
A fixed, external IR wire-frame ported verbatim from third-party tooling and **immutable** — a compatibility contract with non-Aura hardware, with no CRC.
_Avoid_: adding a CRC or altering timings; folding it into the Aura wire-frame

### TagData
The game-layer payload of a tag shot — `team`, `player`, `damage` packed into one opaque byte by the tag codec; game fields live here, never in the wire-frame.
_Avoid_: reading tag fields off the wire-frame; conflating the data codec (`TagData` ↔ byte) with the wire-frame codec (byte ↔ pulses)

### IR emitter
A directed infrared transmit channel; constants `LINE`, `CONE`, `AREA_OF_EFFECT` are the `send_ir` vocabulary, each mapped to its own transmitter. `engine.network.IR_EMITTERS` is the single source of the emitter set.
_Avoid_: importing `magic.CastType` for IR emitters; a default emitter on `send_ir`; restating the emitter key set (derive from `IR_EMITTERS`)

### IR multi-receiver
Several IR receivers, each on its own data line, returning the packet with the lowest **error margin**; improves reception reliability only (no hit direction). Selected by listing **two or more `rx` pins** in `aura-device.json`.
_Avoid_: treating the array as a direction finder; sharing one data line across receivers; a separate config flag to opt in (pin count is the switch)

### IR error margin
The worst-case pulse-timing deviation (µs) tolerated while still decoding a packet; lower is better, and it's the key the multi-receiver uses to pick the best receiver.
_Avoid_: conflating with **IR signal strength** (a normalized derivative, not the raw margin)

### IR signal strength
A normalized 0.0–1.0 quality metric derived from a packet's error margin — a coarse proximity stand-in, not measured power, conveying no direction.
_Avoid_: calling it "RSSI" as if measured; using it to derive hit direction

### IR receive-path telemetry
Monotonic-since-boot counters at each receive-path stage (reader, receiver, decoder), each with exactly one declared owner via a per-class `OWNED_TELEMETRY_FIELDS` tuple whose union is `IrTelemetrySnapshot.FIELDS`; surfaced as an `IrTelemetrySnapshot` and a change-gated `telemetry_line()`.
_Avoid_: aggregating hit/gated counts in the scene; per-tick allocation in the no-pulse path; re-listing the counter set in a receiver (walk the sources)

### Self-echo
The IR pulses a device's own receiver captures from its own emitter while transmitting; decodes as a CRC-valid phantom self-hit, suppressed by the **IR transmit gate**, never by game rules.
_Avoid_: suppressing it in a scene (the old Tag `deafen_until` hack); telling it from a real overlapping shot at the pulse level (indistinguishable — drop both)

### IR transmit gate
The shared coordination primitive (`IrTransmitGate`) that keeps a device from decoding its own **self-echo**: transmitters drive it (`begin_transmit`/`end_transmit`), the receiver reads it through `should_discard()` — `True` while transmitting, then once more on the falling edge.
_Avoid_: a second source of truth for "transmitting"; exposing it on `DeviceHardware`; calling `should_discard()` more than once per tick per receiver

### Drain-but-discard
The receiver's gated-receive contract: while the **IR transmit gate** signals emission, every available pulse is still drained from the reader (so `PulseIn` never overflows) but none is decoded, and any in-progress decode is reset.
_Avoid_: leaving pulses in the buffer to overflow (drain even when discarding); decoding during emission "to catch a real shot"

### Inter-frame gap
The idle period between two IR shots, delivered by `PulseIn` as a single over-long "space" pulse (≈6500 µs+); treated as a frame terminator that abandons a stalled partial decode and returns the decoder to idle.
_Avoid_: trying to "re-arm" or salvage a pulse from an overlapping frame (recognise the gap and start the next frame clean)

### Deploy-watch
The `scripts/deploy_watch.py` host tool that deploys an example and captures the resulting serial run; unlike `deploy.py` it flashes *and* captures.
_Avoid_: treating it as a read-only serial monitor (it overwrites `code.py` and reboots); a no-deploy "just watch" mode

### Reload boundary
The device's soft-reload after `code.py` is written — the line between the stale pre-reload run and the fresh run to capture; found via the **start anchor**.
_Avoid_: assuming it coincides with the deploy finishing (it lags behind it); capturing without anchoring to it

### Start anchor
The known substring marking the **reload boundary** (CircuitPython's soft-reboot banner); capture discards lines until it appears, and fails if it never arrives rather than capturing stale data.
_Avoid_: anchoring on the profiler's `__PROFILE` header (downstream content); proceeding silently when it is missing

### Stop marker
The substring that ends a capture, matched only on **post-anchor** output so it reflects the freshly deployed run; a plain substring, no regex.
_Avoid_: regex; matching against pre-anchor output (a stale-run false stop)
