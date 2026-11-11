# aura-prototype — Domain Language

The canonical code-facing vocabulary for the Aura animation and game-logic engine — one term per entry, with the words to avoid. Magic-system vocabulary (elements, auras, spells) lives in the aura-docs vault.

## Glossary

### Effect
A descriptor declaring which **Modalities** an effect has (pixels, audio, haptic). Builders return plain `Effect` instances — subclass only when there is genuine logic to add.
_Avoid_: `renders_pixels` (use `effect.pixels is not None`); calling `update()`/`render()` directly; an `Effect` subclass that only holds a name; "capabilities" for its modalities (a **Capability** is hardware a device has)

### Modality
One human sense an **Effect** reaches — sight (`EffectPixels`), sound (`EffectAudio`) or touch (`EffectHaptic`). An effect has up to three; a `None` modality means the effect does not reach that sense.
_Avoid_: "capability" (a **Capability** is hardware a device has); "channel" (names a **Console channel** or **Data channel**); "output" (an `EffectOutput` is the hardware side that plays a modality)

### EffectPixels
The **Modality** (sight) that owns pixel simulation and rendering for an effect; `pixels is None` means no pixel output.
_Avoid_: calling `update`/`render` on the `Effect` shell; putting `name` on a compositor (it belongs on `Effect`)

### EffectAudio
The **Modality** (sound) declaring an effect's audio behaviour, mapping **EffectVerb**s to playback configs; `None` means no audio.
_Avoid_: an `EffectVerb.STOP` clips key (teardown is `flush()`, not `handle_event`; rejected at build with a **VerbKeyError**); string keys (rejected)

### AudioPlaybackConfig
A value object for how one clip plays: which clip (a qualified clip name, resolved by the **Active scene namespace** when the effect is built), whether it loops, and whether finishing it stops the whole owning effect (`stops_effect`). Being cut off counts as finishing: a clip whose voice is taken by another sound, or that an **Overlay** covers mid-play, stops its effect just as if it had played out. Declared once at module level and shared by every effect built from it.
_Avoid_: `stop_on_finish`, `end_effect`; reading `stops_effect` as "the sound stops" (it names the effect's end); combining it with `loop=True` (rejected); writing a resolved path onto it (that is a **Resolved clip**)

### Resolved clip
A declared `AudioPlaybackConfig` paired with the WAV path its name resolved to, made when an effect is built and carried on that verb's `EffectEvent`. Owned by the running effect, never shared.
_Avoid_: resolving a clip name in an output; mutating the declared config to hold the path

### EffectHaptic
The **Modality** (touch) declaring an effect's haptic behaviour, mapping **EffectVerb**s to `HapticPattern`s; `None` means no haptic output.
_Avoid_: string keys (rejected); raw DRV2605L waveform IDs as values (hardware IDs live in the output); "vibration" (use `haptic`)

### HapticPattern
A value object holding an ordered sequence of abstract haptic constants — effect constants (`STRONG_CLICK`, …) and pause constants (`PAUSE_250`, …), distinct from hardware waveform IDs.
_Avoid_: raw DRV2605L waveform IDs; `HapticConfig` (collides with the device-config `I2CDeviceConfig` haptics section, which gates hardware presence — a different axis)

### EffectConfig
Runtime configuration passed to effect builders at construction: `resolution`, effect-specific `options`, and `listeners`.

### Effect pack
A named, versioned directory of effect items, each exporting an `EffectBuilder`, whose **Pack manifest** states only its version; shared and cross-scene. It declares no **Settings**: an effect is tuned per use, by the `options` the rule that starts it passes.
_Avoid_: calling a scene-local effect set a "pack" (a pack is shared, versioned, cross-scene); declaring Settings or **Required capabilities** in its manifest (both rejected by the scan)

### Rule pack
A named, versioned directory of rule items, each exporting a `GameRule`, whose **Pack manifest** states its version, declares its **Settings** and lists its **Required capabilities**; shared and cross-scene.
_Avoid_: calling a scene-local rule set a "pack" (a pack is shared, versioned, cross-scene)

### Pack root
A directory whose own name is its top-level import package (flash `packs`, the card's `aura_packs`), holding optional `effects/`, `rules/` and `scenes/` folders. A device has one or two, scanned in order.
_Avoid_: pairing a root path with a hand-written import prefix (the prefix is the folder name); two roots with the same folder name; "pack dir" for a root (a pack dir is one pack inside it)

### PackCatalog
Everything installed under a device's pack roots, discovered in one scan by `scan_pack_roots`: the effect and rule `PackRegistry`s, the `SceneRegistry` (with each scene's local items and sounds), and the pack sounds map. Every scene's pack declarations and **Setting overrides** are checked, and its **Settings** resolved, before it is returned, so a misconfigured layout, version, declaration or override stops boot; item code is still imported lazily, at first use.
_Avoid_: scanning packs, scenes or sounds anywhere else; re-checking scene declarations at load time

### PackScanError
The typed `ValueError` family raised while building a `PackCatalog`, when the files on disk are wrong (missing root, duplicate or reserved name, malformed version, `scene.json` or **Pack manifest**, an **Effect pack** declaring Settings or `requires`, or a scene giving one Setting overrides, a scene declaring a pack twice or declaring one that is missing or incompatible, a **Setting override** naming a Rule pack its scene does not declare or an undeclared Setting, giving the wrong type, or leaving a required Setting unset, or a `requires` list naming an unknown **Capability**). Each carries the file, scene, pack or Setting at fault, so tests check the type and those fields, never the wording.
_Avoid_: confusing with **Registry lookup errors** (a name not registered, after a good scan); classifying by message text; raising one because the device lacks a scene's **Required capabilities** (the scan never looks at hardware)

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
The game context passed to every rule handler each tick: the control seams, the read-only clock, event queuing, and typed accessors for all mutable game data.
_Avoid_: `clear_queue()` from rules (reserved for `SceneManager`); `get(key, None)` (use `get_or_none`); storing a **Setting** in it

### Phase
A named stage of a scene's game flow (e.g. Tag's Ready/Starting/Playing/Game Over), identified by a `PhaseKey`. A phase starts the moment it is entered, in the same tick, whatever order the scene's rules run in; its handlers first hear the event after the one that entered it.
_Avoid_: "state" (collides with `GameState`); "mode" except as the hardware_test label; relying on rule order for when a phase starts

### PhaseKey
An opaque, identity-typed constant naming one phase; compared by identity, so a bare string literal never matches and a typo fails loudly.
_Avoid_: bare `str`/`int` phase values; comparing a phase against a string literal

### PhaseMachine
The mutable per-scene holder of the current `PhaseKey`, the phase-start time, and the dispatch the phase was entered on (so its handlers skip that event); reached through a scene's `PhaseSlot`.
_Avoid_: storing receipts or per-phase scratch on it; auto-stopping effects inside `enter()`

### PhaseSlot
The single per-scene typed accessor owning a phase machine's `GameState` key and initial phase, and knowing which `PhaseRule` owns each phase; all of a scene's phase rules share the *same* instance, so "same key ⇒ same `PhaseMachine`" holds by construction.
_Avoid_: constructing a fresh `PhaseSlot` per rule (import the scene's one); passing a raw machine-key string to a phase rule; confusing it with the generic `StateSlot`; two slots sharing one key

### PhaseRule
A `GameRule` owning one phase's lifecycle: `on_enter`/`on_exit`, phase-gated handlers, and `transition_to`; exactly one per `(machine, phase)`.
_Avoid_: hand-rolled entry flags (use `on_enter`); reaching `super().on(...)` (bypasses the phase guard); transitioning from `on_enter`; transitioning to a phase no `PhaseRule` owns

### InPhaseRule
A `GameRule` whose handlers fire only while a given phase is active, with no lifecycle hooks and no transitions; any number may share a phase.
_Avoid_: making it own or change phases (use `PhaseRule`)

### Setting
A named, typed, immutable start-up value that a scene or a **Rule pack** declares, with a default unless it is required. Resolved once, when the **PackCatalog** is scanned; rules can read it but never change it, and it is kept apart from the runtime game data in `GameState`.
_Avoid_: "tunable", "knob", "initial data", "config key"; keeping a Setting in `GameState`'s `get`/`set` store; seeding runtime game data from `scene.json` (rules seed their own); confusing with the boot values in `aura-boot.json`

### Setting override
A value that replaces a declared **Setting**'s default for one scene: written by the scene for a **Rule pack** it declares, or supplied when the **Simulated device** boots.
_Avoid_: "initial data"; changing a scene's resolved Settings after the scan

### Pack manifest
The JSON file in an **Effect pack** or **Rule pack** that states the pack's version; a Rule pack's also declares its **Settings** and lists its **Required capabilities**, both part of its versioned interface.
_Avoid_: `version.txt`

### Scene Config
A scene's derived, immutable helper object, built once from the scene's **Settings** — e.g. `RlglConfig` scaling durations by Game Level. One per scene (`RlglConfig`, `TagConfig`).
_Avoid_: confusing with `EffectConfig`; calling the Settings themselves the Scene Config; re-deriving it every tick (build once, cache)

### Timer
Owned internally by `GameEngine`. Rules access time only via `state.elapsed`/`state.total`, never by holding a `Timer` reference.

### Scene
A declarative bundle of a self-contained game context: effect/rule packs, its own declared **Settings** and its **Setting overrides** for the Rule packs it declares, a `version`, a declared `ir_codec` name, its own **Required capabilities**, and references to its scene-local effects/rules. Carries no mutable runtime state.

### Capability
One thing a device has that a scene can depend on, named from a fixed vocabulary: a button by label (`button.A`, `button.B`, …), an IR emitter by name (`ir.line`, `ir.cone`, `ir.area_of_effect`), any IR receiver (`ir.receive`), `radio`, `storage`, `accelerometer`, `magnetometer`. A device **has** a capability when what it built provides it — a component declared but not built (disabled, isolated, or its bus failed to open) is not had. Named by component, never by bus or part: an accelerometer on I2C and one on SPI are the same capability.
_Avoid_: "requirement" for one entry (a scene *requires* capabilities); "need", "feature"; naming a bus or part number; "capability" for an **Effect**'s **Modalities**; capabilities for pixels, audio or haptics (effects already cope without them)

### Required capabilities
The **Capabilities** a scene cannot be played without: its own `requires` list in `scene.json` combined with the `requires` of every **Rule pack** it declares (effect packs require nothing). Checked against the device only when the scene is about to run — at boot, and on every transition into it — never for every installed scene at once, so a card can carry scenes for props it is not in. A scene that copes without something simply leaves it out and asks at run time. Adding one to a Rule pack is a major version bump; removing one is minor.
_Avoid_: an "optional" or "uses" list; checking every installed scene at boot; reading a missing capability as a reason to skip game logic in a rule that required it (the check already guaranteed it)

### Capability errors
`UnknownCapabilityError`, a **PackScanError** raised when a `requires` list names something outside the **Capability** vocabulary, carrying the file and the name; and `MissingCapabilityError` (a `ValueError`), raised when the device lacks capabilities something needs right now, carrying the missing capabilities and the scene (`None` for a send). Raised by the boot check once every boot candidate has failed, by a transition into a scene the device cannot run (before anything is persisted or reset), and by `send_ir`/`send_radio` when the emitter or radio is absent.
_Avoid_: classifying by message text; a silent no-op for a send on missing hardware; raising it for a **Persisted scene** the boot can fall back from

### Scene-local effect / Scene-local rule
An effect or rule loaded from an `effects/` or `rules/` subdirectory inside a scene's own folder, private to it and addressed with the reserved `scene.` prefix. Unlike an **Effect pack** it has no version.
_Avoid_: "private pack"; putting scene-only code under `packs/`

### Scene-local sound
A bare `{stem: path}` map of `*.wav` files from a `sounds/` subdirectory inside a scene's own folder — a plain path lookup, not a `SceneLocalRegistry` (no module import, no `scene.` prefix stored). It is installed into the **Active scene namespace** as part of the scene's **Scene view**, where it is addressed by the `scene.` prefix.
_Avoid_: confusing the bare stem key here with the `scene.`-prefixed name a clip is referenced by (the prefix is added at resolution, not stored on the map)

### SceneLocalRegistry
A single-namespace registry for one scene's local effects (or rules), with the same `get`/`items` surface as `PackRegistry` but no version concept.
_Avoid_: modelling scene-local items as a synthetic single-pack `PackRegistry`; calling it a "namespace" (that is the **Active scene namespace**)

### Scene view
What the **Active scene namespace** holds for one scene: its scene-local effects and sounds, and the effect packs it declares. Installed at every transition into that scene.
_Avoid_: "scene part", "scene context"

### Active scene namespace
The names the active scene can reach: its scene-local effects and sounds under `scene.`, plus the shared effect packs (and their sounds) it declares under `<pack>.`. Built once from the **PackCatalog**, its **Scene view** reinstalled by the effect system on every transition, and the one place that says which builder an effect name means and which file a clip name means. Every clip resolves against the active scene, including a pack effect's clips; an effect's own pack grants nothing extra.
_Avoid_: "resolver", "registry" for it; a bypass or "allow everything" mode (demos install a **Scene view** declaring every pack); resolving names anywhere in hardware

### Registry lookup errors
The typed `ValueError` subclasses (`RegistryError` base; `UnknownPackError`, `UnknownItemError`, `MissingItemAttributeError`, `ItemTypeError`) that registries and the **Active scene namespace** raise for lookup failures, typed all the way to the caller so code dispatches on the exception **type** and message wording stays a free display detail.
_Avoid_: classifying a registry failure by `str(exc)`/`startswith` on the message; re-wrapping one as a plain `ValueError`; raising one for a bad disk layout (that is a **PackScanError**)

### Name resolution errors
The **Registry lookup errors** the **Active scene namespace** raises (a grouping, not a class: catch them as `RegistryError`), each naming the full qualified name and its kind (`"effect"` or `"clip"`): `NoActiveSceneError` (no scene installed), `MissingPrefixError` (no `scene.`/`<pack>.` prefix), `UndeclaredPackError` (the pack is installed but the active scene does not declare it), and the shared `UnknownPackError` (no such effect pack installed) and `UnknownItemError` (the pack is known but has no such effect or clip). A clip pack is an effect pack: one with no sounds is still known.
_Avoid_: reporting an undeclared pack as unknown, or the reverse; confusing `UndeclaredPackError` (a name uses a pack its scene did not declare) with `UnknownDeclaredPackError` (a scan-time **PackScanError**: a scene declares a pack that is not installed)

### NetworkControls
The **game-facing**, send-only network seam a rule holds via `GameState.network_controls` (`send_ir`, `send_radio`); the runtime-facing per-tick IR pump lives entirely on `InfraredTransceiver.update()` instead. Both sends raise `MissingCapabilityError` when the emitter or radio is absent.
_Avoid_: putting `poll_transmits()` or any per-tick pump on it (keep the seam send-only); a send that silently does nothing on missing hardware (a rule that copes asks `state.capabilities.has` first)

### SceneRegistry
Serves a fresh `Scene` per lookup from the scenes the **PackCatalog** discovered and checked; it does no scanning of its own. Can also surface a scene's declared codec name without constructing the `Scene`, for callers resolving hardware before building it. `register` is a test-only escape hatch for in-memory scenes, which skip the catalog's declaration checks.
_Avoid_: registering scenes via `SceneManager` (it no longer accepts `register()`); calling `register` outside tests; changing a scene's Settings after the scan (pass **Setting overrides** to the catalog scan); importing codec classes here (the engine stores only the name — see **Wire-frame codec**)

### SceneControls
The scene-transition seam rules use (`overlay`, `pop`, `reboot_into`, `reboot_to_previous`, `can_run`); `SceneManager` is the live implementation. The **Scene boot** hands the same seam to the **Simulation test harness** and the reboot example, which use it as a rule would. Every transition into a scene first checks its **Required capabilities** against the device, and rules can ask whether the device can run a scene before offering it.
_Avoid_: a rule-facing `load` (a rule changes scene by **Reboot**, which starts the new scene clean)

### Overlay
A scene laid temporarily on top of the running scene (a pause, a menu) and removed by `pop`. While it is on top, the scene it covers is suspended: none of its rules run, it hears no events, its game state is kept as it was, and its game time stops, so on `pop` its phases continue from where they were. The covered scene's running effects are set aside, neither drawn nor heard, and given back on `pop` with the same receipts; a looping sound restarts from the top, and a cut-off one-shot is not replayed. An overlay starts on **Split** for every scope, whatever the covered scene chose, and `pop` puts back the covered scene's **Merge strategies**. An overlay runs on the IR codec of the scene it covers, whatever its own `ir_codec` says, so it never breaks the game's traffic. Overlays stack, and each `pop` removes only the top one. It is not a scene switch: the covered scene is still the device's scene.
_Avoid_: "scene switch" for it; counting the time spent covered against the covered scene's phases; a "live" overlay running beside the covered scene (a display over live play is the game's own effects); swapping the codec on overlay or pop

### SceneManager
Owns the scene stack and drives scene transitions, trusting the **PackCatalog** to have checked each scene's pack declarations. Each transition makes one call to the injected `EffectAdmin`, carrying the **Scene view** of the scene it brings to the top; reboots go through the injected `SceneReboot` port. The live `SceneControls`.
_Avoid_: calling `register()` on it (removed); offering rules a way to load a scene in-process (scenes change by **Reboot**); validating pack versions on load or overlay (the catalog already did); routing scene-transition effect calls through `state.effect_controls` (use the injected `EffectAdmin`); holding or installing into the **Active scene namespace** (the effect system does)

### Reboot
The one way a device switches scenes: the target is persisted to device storage, then the device resets and boots that scene. Only storage and what is physically happening to the device (held buttons, motion, where its IR points) carry across; game state, phases and output state do not, and nothing after the reset runs. A device with no SD card cannot persist a target, so it does not reboot, and stays in the scene it booted.
_Avoid_: calling an **Overlay** a scene switch (the covered scene is still the device's scene); switching scenes in-process; "restart", "reload" (reload is CircuitPython's soft reboot after a deploy)

### Persisted scene
The scene a device's card names in `aura-state.json` (`scene`, with its `return_to` companion), written by a **Reboot**. On boot it outranks the flash `default_scene`; a `deploy.py --scene` deploy clears it once, through a new **Scene deploy token**. One the device lacks the **Required capabilities** for is skipped at boot, left on the card, and logged.
_Avoid_: "saved scene", "override" for it; clearing it because this device cannot run it (the card may go back to a prop that can); expecting it to name the running scene right after a `--scene` deploy (the card names none until the next Reboot); treating it as host-authored (only the device writes it)

### Scene deploy token
The per-deploy value `deploy.py --scene` writes as `scene_deploy_token` beside `default_scene` in `aura-boot.json`, new on every invocation. On boot, before the boot scene is resolved, a non-empty token that differs from the one recorded in the card's `aura-state.json` is applied: the **Persisted scene** and its `return_to` are removed and the token recorded, in one write, and one line is logged naming the deployed scene and the Persisted scene it cleared. So each `--scene` deploy wins once, and Reboots made after it keep persisting. The apply never checks the deployed scene against the registry: an unknown one is cleared to, then fails resolution naming the known scenes.
_Avoid_: "nonce", "deploy id" for it; comparing scene names instead (a second deploy of the same scene would be mistaken for the first); copying the deployed scene onto the card; a separate inbox file; applying it outside the **Scene boot**

### SceneReboot
The board-free port `SceneManager` reaches to persist a scene switch and reboot the device; live adapter `DeviceSceneReboot`. Its `previous_scene` names the scene `reboot_to_previous` would boot, so `SceneManager` can check that scene's **Required capabilities** before anything is persisted.
_Avoid_: validating the target here (that is `SceneManager.reboot_into`'s job); calling `microcontroller.reset()` anywhere but the device's entry points (`run_scene` and the on-device reboot example), which pass it to the **Scene boot**

### EffectControls
The **rule-facing** effect seam a rule holds via `GameState.effect_controls`: `set_effect`, `add_effect`, `stop_effect`, `set_merge_strategy`; scene-transition operations live on `EffectAdmin`.
_Avoid_: adding `set_local_effects` or the merge-strategy snapshot lifecycle back onto it

### EffectAdmin
The **scene-transition-facing** counterpart to `EffectControls`, reserved for the scene manager. It has one step per transition, and each step installs the **Scene view** it is given: entering the boot scene starts every scope on **Split**; covering sets the running effects and merge strategies aside as one held bundle (the **Overlay** then starts on Split); uncovering stops the Overlay's own effects and gives that bundle back. `EffectManager` implements both faces.
_Avoid_: calling any `EffectAdmin` step from a `GameRule`; putting it in the rule-facing `EffectControls`; installing a Scene view any other way during a transition; stopping an Overlay's effects yourself before uncovering (uncovering does it)

### Scope
Identifies what a game effect targets, output-agnostically. Leaf scopes: `PERSONAL`, `DIRECTIONAL`, `Global.MAIN/BUFF/DEBUFF`, `AMBIENT`. Composite scopes: `Global.ALL`, `NON_AMBIENT`, `Scope.ALL` (everything — use for teardown).
_Avoid_: `ScopeValue` (implementation artifact); using `AMBIENT` to mean idle effect (it is a routing scope)

### EffectOutput
A hardware or software output registered with the effect system; `receives_pixels = False` for non-pixel outputs (audio, haptic), which skip buffer allocation and render. Told when an effect is held under an **Overlay** (`hold_effect`) and restored on `pop` (`restore_effect`): audio frees the effect's voices and replays its loops on restore, haptics interrupt the current sequence; pixel outputs need nothing, as held effects leave their scopes dark.
_Avoid_: "output" (ambiguous in multi-output contexts); importing it from `engine.effects.manager` (import from `engine.effects.output`)

### EffectEvent
A structured event payload (`pack`, `name`, `verb`, plus the verb's **Resolved clip** or `None`) routed to every in-scope `EffectOutput.handle_event`; `verb` is an **EffectVerb**. `EffectVerb.START`/`STOP` are emitted automatically, custom verbs (`PulseEffect.PEAK`, `LightningEffect.STRIKE`) via `notify_listeners`. Its identity is `pack`, `name` and `verb`; the clip is payload.
_Avoid_: confusing with `Event` (game-rule events); assuming only `EffectVerb.START`/`STOP` exist

### EffectVerb
A named moment an **Effect** announces to its outputs, and the key for `clips` and `patterns`: `EffectVerb.START`/`STOP` from the engine, plus the custom verbs its sight modality declares (`PulseEffect.PEAK`, `LightningEffect.STRIKE`). Matched by identity, so only the declared instance counts. Heard by outputs, never by rules. An effect pack's declared verbs are part of its versioned interface.
_Avoid_: string keys; a hand-made `EffectVerb("…")` outside its emitter; "event name"; "verb" unqualified where SD-sync protocol verbs are nearby; treating an **Overlay**'s hold/restore as verbs; reusing it for game-rule `Event`s (rules match those by class)

### VerbKeyError
The `ValueError` that `set_effect`/`add_effect` raise, before anything in scope stops, when a built effect keys `clips` or `patterns` on a verb it can never emit (anything but `EffectVerb.START`, `EffectVerb.STOP` and its pixels' `VERBS`), or keys a clip on `EffectVerb.STOP`. Carries the qualified effect name, the modality (`"clips"`/`"patterns"`), the offending verb and the verbs the effect emits (ADR-0006).
_Avoid_: confusing with **Registry lookup errors** (every name resolved; the key is wrong); rejecting a `STOP` haptic pattern (allowed: an effect may buzz as it ends)

### Merge strategy
The per-scope policy deciding how a scope's stack of layered effect buffers becomes shown pixels; set per rule via `EffectControls.set_merge_strategy`, defaulting to **Split**. A booted scene and every **Overlay** start on Split; popping an overlay puts back the strategies of the scene it covered. Two ship: **Split** and **Additive**.
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

### AudioEffectOutput
A CircuitPython `EffectOutput` driving audio via I2S and the live `VoiceSink` adapter: it plays the path on each event's **Resolved clip**, owns the hardware (amp, mixer, WAV sources) and delegates voice-slot bookkeeping to a `VoicePool`.
_Avoid_: stopping playback in `handle_event` on `EffectVerb.STOP`; assuming a fixed voice count or role-assigned slots; putting slot bookkeeping back in the output; resolving clip names (the event already carries the path)

### VoicePool
A hardware-agnostic owner of audio voice-slot bookkeeping (imports no CircuitPython), driving hardware through a `VoiceSink` port and evicting oldest-first when full. `hold` frees a held effect's voices (a cut-off `stops_effect` one-shot stops its receipt, as on eviction) and `restore` plays its held loops again from the top.
_Avoid_: importing CircuitPython audio libs here (hardware lives behind `VoiceSink`); parallel per-slot lists (use the `_Slot` record)

### VoiceSink
The port through which `VoicePool` reaches audio hardware (live CircuitPython mixer + a recording test fake); applies loudness and owns `max_volume`.
_Avoid_: passing a pre-multiplied hardware level across the seam (pass `0..1` loudness); leaking receipts through the port

### Drv2605EffectOutput
A CircuitPython `EffectOutput` driving a DRV2605L haptic driver on all scopes (`receives_pixels = False`); translates `HapticPattern` constants to waveforms, a new event interrupting the current sequence.
_Avoid_: constructing with a `None` driver; reading `receipt.loudness` (the DRV2605L has no volume control); "motor" for the injected instance (use `driver`)

### aura-device.json
The single **required** on-device file holding all hardware configuration; a missing file raises. Sections: `buttons`, `ir`, `pixels`, `audio`, `i2c`, `spi`, `radio`, `sdcard`, `high_current_rail`, `neopixel_current_budget`, `accelerometer`, `magnetometer`, `haptics`. `pixels` and `buttons` are each an optional, possibly-empty list. Pure hardware config — scene selection lives in **`aura-boot.json`** instead.
_Avoid_: `settings.toml` (removed — unreadable on MicroPython); keying the pixel section `output`; putting `board` pin objects in the file; adding a `scene` field to `DeviceConfig`; a top-level `"scene"` key (moved to `aura-boot.json`)

### aura-boot.json
The single **required** on-device flash file holding the device's **boot values**: start-up values, mostly written by `deploy.py`, that choose the boot scene and never reach `GameState`. Drag-editable over USB alongside `aura-device.json`; a missing file raises. Carries the `default_scene` key — named for its *default*-selection role, since the card's **Persisted scene** layers on top of it — and, once `deploy.py --scene` has run, the **Scene deploy token** (`scene_deploy_token`, optional; hand-authored files omit it).
_Avoid_: reading `default_scene` from `aura-device.json` (moved out); treating a stale `"scene"` key left in an old `aura-device.json` as meaningful (it is inert); hand-editing `default_scene` to change the boot scene (without a new token it does not displace a Persisted scene — `deploy.py --scene` is the supported path); `aura-settings.json` (the old name, read nowhere: a board still carrying only it fails at boot until fixed by hand); "settings" or "device settings" for boot values (those words name a scene's or pack's **Setting**)

### DeviceConfig
The validated value object parsed from an `aura-device.json` mapping — no `board` import, constructs no hardware. Can derive an isolated copy with every isolatable component but one disabled, for single-component bring-up. Never changed once parsed — a different config is a different mapping, parsed again, so every config satisfies its `NeoPixelCurrentBudgetConfig`; `isolate` is the one derivation, because it only narrows.
_Avoid_: importing `board` into the parser; constructing hardware in the parser (that is the **Device assembly**'s job); hand-listing the isolatable components (derive from `__slots__`); assigning to a parsed config or its sections

### HighCurrentRailConfig
The parsed config for the board's high-current rail enable pin — the line gating the ~2 A NeoPixel rail (and any peripheral drawing more than a GPIO's own budget). Infrastructure rather than a component: excluded from `isolate`, and its `enabled: false` still drives the pin deasserted rather than building nothing (see **Component enabled toggle**).
_Avoid_: `power`/`external power` (too generic — this is only the switched high-current subset, not board power); treating it like `SDCardConfig`'s `enabled` (build-nothing); assuming `isolate(keep=...)` ever disables it

### NeoPixelCurrentBudgetConfig
The opt-in, parse-time cap on the total worst-case NeoPixel current (every enabled NeoPixel strip at full white, at its declared brightness), dimming strips to fit and never below a **minimum brightness** floor; strips declared at or below that floor are left as declared. Policy rather than a component: it builds no hardware, has no `enabled` toggle (presence is the switch), and is excluded from `isolate`. Budgets the NeoPixel draw only, within the rail `HighCurrentRailConfig` gates.
_Avoid_: `neopixel_power`/`power budget` (too generic, see `HighCurrentRailConfig`); reading it as a live current limit or measurement (it is a static arithmetic bound fixed at boot); counting the matrix or disabled strips against it; expecting relative brightness between strips to survive once a strip is held at the floor

### Component enabled toggle
The optional `enabled` boolean on every hardware component config (default `True`); `enabled: false` keeps a fully-validated section but tells the **Device assembly** not to build it. `buttons` is a bare pin-name list and isn't gated; a **Named bus** has no toggle of its own; `high_current_rail` is the exception (still drives its pin deasserted — see `HighCurrentRailConfig`).
_Avoid_: treating `enabled: false` as omitting the section at parse time (validation still runs in full); writing `.enabled` after parse (to narrow, use `isolate`; to force a section on, set `enabled` in the mapping and parse again); assuming `high_current_rail`'s `enabled: false` means "build nothing" like every other section

### Named bus
One physical I2C or SPI bus declared once, under a name, in the `i2c` or `spi` section of **aura-device.json**. A device joins a bus by naming it, and devices that name the same bus share it. A device that names no bus joins the bus named `default`, which is the board's own bus unless `default` is declared. Only buses that an enabled device names are opened.
_Avoid_: repeating bus pins inside a device section; "shared bus" for the whole section (one section can declare several buses); calling a second bus an "override"; a per-bus `enabled` toggle (disable the bus's devices instead)

### Composition layer (app/)
The top-level `app/` package — the one place allowed to import both engine runtime machinery and `hardware.*` together. It composes the board-free engine/effect/scene machinery (CPython-testable) and wires it to real hardware for the per-tick loop.
_Avoid_: importing `hardware.*` from `engine/`, `effects/`, `magic/`, `packs/`; putting board-only code in `scene_composition.py`

### Scene boot
The one boot the device and the **Simulated device** share, and the **Composition layer**'s only way in. From the hardware a device built, it applies a pending **Scene deploy token**, then picks the boot scene (the **Persisted scene**, else the flash `default_scene`), skipping one the device lacks the **Required capabilities** for and raising when none fits. It applies that scene's wire-frame codec before the first tick, and hands back the booted scene's name, its tick, its **SceneControls** and its **Active scene namespace**. Card content is scanned exactly like flash content. Each boot builds one tick, whose buffers are allocated once and reused every tick.
_Avoid_: sequencing the boot's steps at a call site; a second boot for tests or examples; scanning packs or scenes outside it; copying the tick's body into a harness or entry point; building a tick per frame; reading `ir` or `radio` anywhere but `DeviceHardware`; "startup", "init" for it

### SceneRuntime
The engine's matched set for running scenes, built once from the **PackCatalog** and what the device offers (its effect outputs, network controls, **Capabilities** and **SceneReboot**): one **Active scene namespace**, the effect system that resolves through it, and the scene manager that drives transitions. A tick queues its events on it and updates it once; that dispatches the events, applies any pending **Overlay** or pop, then updates effects, on one clock.
_Avoid_: wiring the namespace, effect manager, game engine and scene manager by hand; driving its parts separately within a tick; more than one per device; "engine" for it (the game engine is one of its parts)

### Device assembly
The board-free turning of a `DeviceConfig` into a `DeviceHardware`, shared by the physical device and the **Simulated device**: which components are built or skipped, which need a bus, the order they come up in, how each is narrated, and how the IR and radio subsystems are wired. It reaches hardware only through **DeviceParts**, so a config the board rejects for config reasons is rejected in simulation too.
_Avoid_: builder (names the device-only entry point); repeating gating or IR wiring in a `DeviceParts` adapter

### DeviceParts
The port **Device assembly** reaches leaf hardware through — one constructor per part (pins, buses, pixels, buttons, sensors, audio, haptics, IR pulse readers and writers, radio transport, storage), taking pin names rather than pin objects. One adapter per platform, so a new platform (CircuitPython today; MicroPython or a Linux single-board computer later) adds an adapter, not a builder: `CircuitPythonParts` on a board, and the **Simulated device**'s `SimulatedParts`, which also decides which parts persist across a **reboot**.
_Avoid_: leaves, leaf factory; deciding enabled/declared or bus requirements in an adapter (that is the assembly's job)

### device_builder
The device-only entry point that runs **Device assembly** with `CircuitPythonParts`. Single-call (claims pins without deiniting); every component is config-gated, never presence-probed.
_Avoid_: returning a bare tuple/dict (return `DeviceHardware`); putting config parsing here (lives in the pure parser); calling it twice in one process

### DeviceHardware
The board-free bundle `build_hardware` returns — a data holder for the built outputs, buttons, sensors, network seam, `ir`, `radio`, and storage, plus the **Capabilities** the device has and the ordered **Polled parts**, both worked out once by **Device assembly** from what it built. Ports are typed as their abstract port, never the concrete adapter, keeping the module board-free.
_Avoid_: exposing raw transmitters (use `network_controls`/`ir`); exposing the raw `RadioTransport` (use `network_controls`/`radio`); a bare tuple/dict; downcasting `storage` to `SdCardStorage`

### Simulated device
A board-free, test-only stand-in for a physical Aura device: a `DeviceHardware` whose inputs are scripted and whose outputs record what the real device would show, play, buzz, and send. Its own emitters light its own receivers; its IR reaches other simulated devices only through the **IR medium**, where it is aimed, and its radio reaches every other one through the **radio medium**. Each has its own radio node, so a receiver can tell senders apart. Its shape comes from a `DeviceConfig` — the harness boots it from `examples/aura-device.simulated.json`, kept capability-equal to every other example config by a sync test. It has its own card, a real directory it can carry scenes and packs on, unless a test makes it card-less, and a **reboot** boots it again at once, within the tick that reset it. A test switches it on into a scene: that seeds its boot values with that scene as `default_scene`, and every boot, the first included, reads those boot values, picking the scene its card names and falling back to that default, as a real device does. A redeploy with a scene replaces that `default_scene` and adds a fresh **Scene deploy token**, then reboots it, as `deploy.py --scene` followed by a reset would; a plain reset keeps the boot values it has. Its reboot is instant: a real device is away for a moment while it boots, and IR aimed at it then is lost, but a simulated one never is. Its reboot also keeps module-level state, which a real reset clears, so shipped code keeps none. When real hardware exposes a bug it missed, the simulated device is extended until that bug is visible.
_Avoid_: mock device, virtual device, emulator (it does not run CircuitPython); faking the CircuitPython libraries beneath `device_builder`; hard-coding its hardware shape (declare it in the simulated config)

### Simulation test harness
The test-only fixture layer that boots real scenes on one or more **simulated devices**, drives them through scripted inputs and time, and answers questions about what each device observably did. Tests written on it state behaviour, not the engine calls that produce it. A test can build a device without some **Capabilities** (without `storage` it is card-less) or hand it a card it prepared, follow it through each **reboot** into the scene it runs next, redeploy it with a scene, and cover its scene with an **Overlay** and pop it, as a rule would. At most one card in a simulation may carry packs, and a closed simulation leaves no trace of its cards for the next.
_Avoid_: device harness, scene harness (both read as runtime code); asserting on which effect names a rule passed to `EffectControls`

### Aim
A test's standing statement that one simulated device's IR emitter reaches a set of other simulated devices, optionally only some of their receivers; it holds until replaced, and a new device starts aimed at nobody.
_Avoid_: link, target, line of sight (no geometry is modelled); "connect" (there is no connection, only reach)

### IR medium
The simulation's carrier of IR pulses between simulated devices: what an emitter sends during one tick lands at the start of the next on every device it was aimed at when sent (a later aim does not redirect pulses already in flight), queued in a fixed order with no collisions.
_Avoid_: network, channel (collide with the radio and the network seam); "air"

### Radio medium
The simulation's carrier of radio packets between simulated devices: what a device sends during one tick reaches every other simulated device at the start of the next, with no aim, as a broadcast reaches every device on the frequency; a device never hears its own send. Packets from several senders queue in a fixed order with no collisions or loss, and each device takes one per tick.
_Avoid_: network, channel (collide with the network seam and the chip's one channel); aiming radio (broadcast has no direction)

### Shade
A pixel showing a dimmed version of one colour (the colour scaled toward black, hue unchanged); a strip whose lit pixels are all shades of red shows only red, at any brightness. Dark pixels are no colour's shade.
_Avoid_: tint, hue (both read as other colour operations); bit-masking a pixel against a channel in a test (ask whether it is a shade instead)

### RadioTransport
The board-free half-duplex radio **port** `RadioTransceiver` reaches the chip through — one port for both directions because an RFM69-class chip is half-duplex. The live adapter is `Rfm69RadioTransport`.
_Avoid_: splitting it into send/receive ports; importing `adafruit_rfm69` here (that lives in the adapter)

### RadioTransceiver
The board-free single owner of a device's whole radio subsystem, exposed as `DeviceHardware.radio`; the network seam's `send_radio` delegates to it. A send is fire-and-forget on the single channel — no emitter to name, unlike IR — and it builds no game event itself.
_Avoid_: a transmit pump or pump-before-receive order; a value-returning `update()` (read `received`/`last_sender`); building `NetworkEvents.RadioReceived` here (that's `run_scene`'s job)

### Rfm69RadioTransport
The live CircuitPython `RadioTransport` adapter wrapping `adafruit_rfm69.RFM69` — the only module importing that library.
_Avoid_: importing `adafruit_rfm69` anywhere else; reading the driver without checking `payload_ready` first (blocks)

### DeviceStorage
The board-free device-state storage port: reads/writes small state files under a mount root and resolves real filesystem paths for streamed/scanned consumers. Live adapter `SdCardStorage`; tests and the **Simulated device**'s card run the same storage over a temporary directory.
_Avoid_: escaping the mount root; a second concrete implementation for CPython vs. CircuitPython (one class suffices once mounted); using `path("")` where the clean root is needed (use `mount_root`)

### SdCardStorage
The live CircuitPython `DeviceStorage` adapter that mounts an SD card at construction — the only module importing `sdcardio`/`storage`.
_Avoid_: importing `sdcardio`/`storage` anywhere else; wrapping `cs` in `digitalio.DigitalInOut`; presence-probing instead of trusting the config gate

### SdSyncServer
The board-free device side of the SD-sync protocol; serves file read/write/list requests against a `DeviceStorage` over an injected `Transport`, replying in-band when no SD is configured.
_Avoid_: raising for "not found"/"no SD configured" (reply in-band instead — both are routine, not programming errors); asserting its wire-format internals in tests (assert only external behaviour: bytes read, responses returned); pinning a real connection to one verb (drive `serve_one` instead)

### SdSyncClient
The board-free (CPython-only) host side of the SD-sync protocol; drives an `SdSyncServer` over an injected `Transport` to pull, push, and list files, verifying a whole-file CRC-32 and surfacing the server's in-band failures as loud, typed errors.
_Avoid_: opening the host file before the server confirms the pull will proceed (leaves an empty file on a "not found"); treating a CRC mismatch as chunk-level (it is whole-file, so a retry re-runs the entire transfer)

### SD-sync `Transport`
The board-free port `SdSyncClient`/`SdSyncServer` exchange base64-framed lines through, one `Frame` at a time. Live adapters are `UsbCdcTransport` (device) and `SerialTransport` (host); an in-memory loopback stands in for CI.

### UsbCdcTransport
The live device-side `Transport` adapter, newline-framing SD-sync lines over a serial-like stream. Duck-typed against any `read`/`write` stream — it imports no `usb_cdc`, so it is CPython-testable against a fake stream.
_Avoid_: importing `usb_cdc` into this module (the device-only wiring lives in `examples/sd_sync.py`); assuming the wire grammar is a stable contract (it's a free implementation detail, not asserted in tests)

### SerialTransport
The live host-side SD-sync `Transport`, newline-framing lines the same way as `UsbCdcTransport` but over a host serial port. Byte-framed over the **data channel**, distinct from `deploy_watch`'s UTF-8 **console channel**.
_Avoid_: reusing `deploy_watch`'s `iter_serial_lines` for SD-sync (it decodes UTF-8 and targets the console channel, not the byte-framed data channel)

### Console channel
The USB-CDC serial channel a board always exposes for REPL and `print` output; what **Deploy-watch** captures.
_Avoid_: "REPL port", "the usbmodem port", or bare "serial port" (ambiguous once the data channel is enabled)

### Data channel
The second USB-CDC serial channel a board exposes when enabled on the device, carrying SD-sync protocol bytes rather than text.
_Avoid_: "CDC2", "the other port", bare "serial port"

### Port auto-detect
Resolution of a host serial port for one named channel (**console channel** or **data channel**) by asking which board interface it is: a single match auto-selects, an explicitly named port overrides without scanning, and zero or multiple matches fails loudly.
_Avoid_: picking a port by device-name pattern (both channels look alike); falling back to "the only usbmodem device" when no channel matches; guessing among multiple matches

### NeoPixelEffectOutput
A CircuitPython `EffectOutput` driving **one** NeoPixel strip, subdivided into scope **segments** by pixel range; several strips may share a scope and are driven in sync.
_Avoid_: the old per-scope shape (one strip per `Scope`); conflating segment length with `min_resolution`; a brightness field on this output; overlapping segments on one strip

### Accelerometer
A hardware sensor providing 3-axis acceleration readings (x, y, z) in m/s²; optional, absent when hardware is not present.
_Avoid_: "IMU" (the LIS3DH has no gyroscope or magnetometer)

### Polled part
A built part the tick refreshes exactly once per tick by calling `update(elapsed)`, after which it holds its own state for the tick to read: buttons, accelerometer and magnetometer hold a standing `reading`; IR and radio hold this tick's `received` packet, or `None`. **Device assembly** lists each Polled part as it builds it, and the tick polls that list rather than naming parts, so a part that is built is a part that is polled. Polled parts never depend on the order they are polled in within a tick.
_Avoid_: passing a caller-owned buffer into `update` (the part owns its state); polling a part by name in the tick; one Polled part reading another's state within the same poll

### PolledSensor
The board-free **Polled part** wrapping one sensor's raw read: each poll refreshes its `reading` in place from the raw read, and a failed read keeps the last good reading; the start and end of a run of failed reads are logged. It does not know the reading's shape — the reading assigns a raw read to itself — so one PolledSensor serves the accelerometer and the magnetometer alike. A device with no such hardware has no PolledSensor in its place, which is distinct from a failed read.
_Avoid_: `Sensor` (buttons and IR receivers are sensors too); swallowing read failures at the call site; allocating a new reading per poll

### AccelerationData
A snapshot of 3-axis accelerometer readings; `None` when no accelerometer is present — signals "no sensor data," not "device at rest."
_Avoid_: `MovementData`

### Magnetometer
A hardware sensor providing 3-axis magnetic field readings (x, y, z) in microteslas (µT); optional, absent when hardware is not present.
_Avoid_: "IMU" (the MMC5603 has no gyroscope or accelerometer)

### MagneticData
A snapshot of 3-axis magnetometer readings in microteslas (µT), in the magnetometer's raw chip-native frame (unremapped); `None` when no magnetometer is present — signals "no sensor data," not "zero field" and not "read failed."
_Avoid_: "IMU" (magnetometer is a separate sensor from the accelerometer)

### ButtonData
A snapshot of button states, each one of `UP`, `DOWN`, `PRESSED` (down this frame), `RELEASED` (up this frame); query methods return `bool`, and `is_down` is `True` on both `PRESSED` and `DOWN`.
_Avoid_: reading `_states` directly (use the query methods); assuming `is_down` excludes the `PRESSED` frame

### IR transport
The hardware-agnostic infrared send/receive subsystem (no `pulseio`), reached through `PulseReader`/`PulseWriter` ports; moves opaque `bytes` with no game semantics.
_Avoid_: importing `pulseio` into shared IR code; encoding spell fields in the transport

### InfraredTransceiver
The board-free single owner of a device's whole IR subsystem — the transmitter map, the receiver, and the shared **IR transmit gate** — exposed as `DeviceHardware.ir`; the network seam's `send_ir` delegates to it. A send routes to the named emitter, and it builds no game event.
_Avoid_: importing `NetworkEvents`/game-event vocabulary here (the event is built in `run_scene`); a value-returning `update()`; calling it a hardware "driver"; exposing the transmitter map as a public collection

### Wire-frame codec
An encoder/decoder pair mapping an opaque payload ↔ IR pulse durations, injected into the IR transport; two coexist — the **Aura wire-frame** and the **Tag protocol** — selected by the scene a device boots; an **Overlay** runs on the codec of the scene it covers. Travels as a class pair, so each receiver reader gets its own fresh decoder. A built device's codec is mutable once, at boot, via `InfraredTransceiver.apply_codec`, which hands the installed pair back read-only.
_Avoid_: assuming a single global wire-frame; treating wire-frames as interchangeable across scenes; passing codec instances (one decoder must never be shared between readers)

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

### InfraredReceiver
The one board-free receiver that reads every IR receiver on a device through that receiver's own pulse reader and decoder, for any number of readers; surfaces at most one packet per tick, the one with the lowest **IR error margin**, and names the winning reader only when there was a pick to make. On its own, "IR receiver" means the physical sensor on one data line.
_Avoid_: separate single- and multi-receiver classes; branching on reader count to choose a receiver; sharing one decoder between readers

### IR error margin
The worst-case pulse-timing deviation (µs) tolerated while still decoding a packet; lower is better, and it's the key the multi-receiver uses to pick the best receiver.
_Avoid_: conflating with **IR signal strength** (a normalized derivative, not the raw margin)

### IR signal strength
A normalized 0.0–1.0 quality metric derived from a packet's error margin — a coarse proximity stand-in, not measured power, conveying no direction.
_Avoid_: calling it "RSSI" as if measured; using it to derive hit direction

### IR receive-path telemetry
Monotonic-since-boot counters at each receive-path stage (reader, receiver, decoder), each with exactly one declared owner; surfaced as an `IrTelemetrySnapshot` and a change-gated `telemetry_line()`.
_Avoid_: aggregating hit/gated counts in the scene; per-tick allocation in the no-pulse path; re-listing the counter set in a receiver (walk the sources)

### Self-echo
The IR pulses a device's own receiver captures from its own emitter while transmitting; decodes as a CRC-valid phantom self-hit, suppressed by the **IR transmit gate**, never by game rules.
_Avoid_: suppressing it in a scene (the old Tag `deafen_until` hack); telling it from a real overlapping shot at the pulse level (indistinguishable — drop both)

### IR transmit gate
The shared coordination primitive that keeps a device from decoding its own **self-echo**: transmitters mark when they are emitting, and the receiver discards while emission is active plus once more on the falling edge.
_Avoid_: a second source of truth for "transmitting"; exposing it on `DeviceHardware`; calling `should_discard()` more than once per tick per receiver

### Drain-but-discard
The receiver's gated-receive contract: while the **IR transmit gate** signals emission, every available pulse is still drained from the reader (so `PulseIn` never overflows) but none is decoded, and any in-progress decode is reset.
_Avoid_: leaving pulses in the buffer to overflow (drain even when discarding); decoding during emission "to catch a real shot"

### Inter-frame gap
The idle period between two IR shots, delivered by `PulseIn` as a single over-long "space" pulse (≈6500 µs+); treated as a frame terminator that abandons a stalled partial decode and returns the decoder to idle.
_Avoid_: trying to "re-arm" or salvage a pulse from an overlapping frame (recognise the gap and start the next frame clean)

### Deploy-watch
The host tool that deploys an example and captures the resulting serial run; unlike `deploy.py` it flashes *and* captures.
_Avoid_: treating it as a read-only serial monitor (it overwrites `code.py` and reboots); a no-deploy "just watch" mode

### Reload boundary
The device's soft-reload after `code.py` is written — the line between the stale pre-reload run and the fresh run to capture; found via the **start anchor**.
_Avoid_: assuming it coincides with the deploy finishing (it lags behind it); capturing without anchoring to it

### Start anchor
The known substring marking the **reload boundary** (CircuitPython's soft-reboot banner); capture discards lines until it appears, and fails if it never arrives rather than capturing stale data.
_Avoid_: anchoring on content the deployed program prints (downstream of the boundary); proceeding silently when it is missing

### Stop marker
The substring that ends a capture, matched only on **post-anchor** output so it reflects the freshly deployed run; a plain substring, no regex.
_Avoid_: regex; matching against pre-anchor output (a stale-run false stop)
