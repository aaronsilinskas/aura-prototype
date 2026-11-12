# Domain: aura-prototype

## What this project is

`aura-prototype` is the Python/CircuitPython/MicroPython animation and game-logic engine for the **Aura** live-action game platform. Aura is a physical magic game played with custom props (wands, targets, tokens) powered by microcontrollers.

This repo implements:
- A composable LED animation engine (`effects/`) that runs on both CPython and CircuitPython
- Game rules for a magic system built around ten elements (Fire, Water, Earth, Ice, Air, Lightning, Light, Dark, Time, Gravity)
- An event-driven game engine (`engine/`)
- Spell and aura logic (`magic/`)

Full game and hardware design lives in `~/dev/aura/aura-docs/` (an Obsidian vault). Key references for agents:
- `Overview/Magic System.md` — element definitions, buffs/debuffs, spell mechanics
- `Overview/Design Principles.md` — core game design goals
- `Reference/Props and Hardware.md` — physical device inventory

---

## Module layout

```
effects/          Animation engine (CircuitPython-safe)
  effect.py       EffectConfig, PixelBuffer, Effect, EffectPixels, EffectAudio, EffectHaptic,
                  EffectVerb, AudioPlaybackConfig, ResolvedClip, HapticPattern
  palette.py      Palette, PaletteLUT256 (pre-computed, immutable)
  shape.py        Shape (factory), EffectShapeFunc
  level.py        EFFECT_TOP_LEVEL, effect_level (the Effect Level's range and
                  its one read; no interpolation, builders use engine/lerp.py)
  value.py        DynamicValue, ValueGenerator, lerp
  layers/         Layer base class + scroll, flame, drift_noise, sparkle, shape, progress, pulse
                  layers and the renderers

engine/           Event-driven game loop (CircuitPython/MicroPython-safe)
  engine.py       GameRule
  state.py        GameState, SceneRun, EffectControls, EffectReceipt, MergeStrategy,
                  NetworkControls, Scope, ScopeValue
  scene.py        Scene, SceneRegistry, SceneLocalRegistry, SceneManager, SceneControls
  scene_runtime.py SceneRuntime (the matched set built from a PackCatalog; above scene
                  and pack_catalog in the import graph)
  phase.py        PhaseKey, PhaseMachine, PhaseSlot, PhaseRule, InPhaseRule
  events.py       Event, EventGroup, EffectEvent
  timer.py        Timer
  lerp.py         level_lerp, level_lerp_int (the one level interpolation, for Game and
                  Effect Levels: level, value at level 1, value at the top level, top level)
  packs.py        PackRegistry, RegistryError family (lookup-time)
  pack_catalog.py scan_pack_roots, PackCatalog, PackScanError family (scan-time)
  scan_error.py   PackScanError base, kept apart so capabilities.py stays importable by hardware
  capabilities.py Capability vocabulary (is_capability), the Capabilities view rules ask,
                  UnknownCapabilityError, MissingCapabilityError (board-free; shared by
                  scan, device, GameState and harness)
  settings.py     Settings (read-only view), Setting declaration parsing and resolution
  version.py      Pack MAJOR.MINOR parsing
  input.py        ButtonData, AccelerationData, MagneticData, InputEvents
  namespace.py    ActiveSceneNamespace; NoActiveSceneError, MissingPrefixError, UndeclaredPackError
  network.py      NetworkEvents
  log.py          Board-free, tag-prefixed line logger with an injectable sink
  effects/
    admin.py      EffectAdmin, HeldEffects, SceneView (scene-transition face; hardware can't reach it)
    builder.py    EffectBuilder
    manager.py    EffectManager; VerbKeyError
    output.py     EffectOutput (abstract hardware output port)
    merge.py      SplitMerge, AdditiveMerge (per-scope layered-buffer compositing;
                  subclass state.py's MergeStrategy)

magic/            Spell and aura game logic (CircuitPython/MicroPython-safe)
  aura.py         Aura, Spell, Spells, SpellTags, SpellLevelScaler, AuraEvent (+ subclasses), EventListener
  caster.py       Caster, CastType (LINE / CONE / AREA_OF_EFFECT)
  values.py       MinMaxValue, ValueWithModifiers, ValueModifier, ValueModifiers, Duration, Counter
  spell/          Individual spell implementations (elemental/, combo/, ambient_magic_regen)

packs/            Game-specific packs loaded at runtime (CircuitPython/MicroPython-safe)
  effects/        Shared, versioned effect packs (basic, elements) — each with an effects.json manifest
  rules/          Shared, versioned rule packs (debug, lobby, return_to_lobby) — each with a rules.json manifest;
                  lobby and return_to_lobby require button.A, button.B and storage, and the lobby
                  offers only the entries SceneControls.can_run accepts
  scenes/         Scene definitions (element_browser, example_lobby, hardware_test,
                  ir_range_receiver, ir_range_transmitter, red_light_green_light, tag);
                  each has a scene.json and optional scene-local effects/ and rules/ subdirs

hardware/         Hardware abstraction layer
  circuitpython/  CircuitPython drivers (device_builder: build_hardware, the device
                  entry point that runs the Device assembly; circuitpython_parts:
                  CircuitPythonParts, its DeviceParts adapter; is31fl3741_output,
                  drv2605_output, neopixel_output, audio_output, infrared_io,
                  pio_pulse_writer, rfm69_radio_transport,
                  sdcard_storage, usb_cdc_transport, boot)
  shared/         Hardware-agnostic helpers (matrix_output, voice_pool, debounced_buttons,
                  device_config, neopixel_current_budget, device_boot, device_state,
                  device_hardware,
                  device_storage, network_controls, scene_selection, ir_transport,
                  ir_transceiver, ir_codecs/ (base, aura, tag), ir_telemetry,
                  radio_transport, radio_transceiver, sd_sync_protocol, sd_sync_server,
                  device_reboot, device_assembly (the Device assembly),
                  build_narration, device_parts, polled_part, polled_sensor)
  simulated/      Test-only Simulated device (device: SimulatedHardware; simulated_parts:
                  SimulatedParts, its DeviceParts adapter, whose card is the real
                  DeviceStorage over a card directory) — never deployed

app/              Composition layer — the one place allowed to import both the engine's
                  runtime machinery and hardware.* together
  scene_composition.py  The Scene boot: build_scene_boot and the SceneBoot it returns
                        are its whole interface (board-free, CPython-testable); the
                        device and the Simulated device share both the boot and the
                        tick, which polls DeviceHardware.polled. Boot runs the Persisted
                        scene, else flash default_scene, skipping one the device lacks
                        the Required capabilities for (raises MissingCapabilityError
                        when none fits)
  run_scene.py          run_scene (device-only: bring-up, build_scene_boot, then loops
                        the tick it returns)
  simulation/           Test-only Simulation test harness (Simulation, SimulatedDevice):
                        boots real scenes on simulated devices, reboots them
                        through their cards, real directories a test can put
                        card scenes and packs on, and carries aimed IR
                        between them (the IR medium) and radio to every other
                        device with a radio (the radio medium); add_device(
                        without={...}) drops Capabilities from the simulated
                        config (without={"storage"} is card-less); a test can
                        cover a device's scene with an Overlay and pop it —
                        never deployed

examples/         Runnable CircuitPython entry points; deploy-watch's flash targets

scripts/          Deploy and maintenance scripts (CPython-only)

electronics/      PCB design source (KiCad) — scratch/, pcbs/, libraries/, each with
                  its own README.md. Distinct from the hardware/ firmware package
                  above: electronics/ is design source, not Python, contains no
                  package, and carries no import-linter contracts — it sits outside
                  the engine ↔ hardware layering described below entirely.
```

### Module layering

The `engine` ↔ `hardware` boundary is one-way and enforced by `import-linter`
(`[tool.importlinter]` in `pyproject.toml`, run via the `lint-imports`
pre-commit hook on every commit):

- `engine` must never import `hardware` (total, one-way).
- `hardware` must never import engine runtime machinery — `engine.engine`,
  `engine.scene`, `engine.packs`, `engine.namespace`, `engine.timer`,
  `engine.effects.manager`. Hardware never resolves effect or clip names; it
  plays the path on each event's resolved clip (ADR-0002).
- `app/` is the sole sanctioned crossing point: the one place allowed to
  import both the engine's runtime machinery and `hardware.*` together (see
  **Composition layer (app/)** in `GLOSSARY.md`).
- No shipped module may import the test-only `app.simulation` or
  `hardware.simulated`; only `tests/` packages may. The **Ship list**
  (`scripts/ship_list.py`) leaves both directories out, so they never
  reach a device.

---

## Key types and relationships

A map of where the major types live. Authoritative term meanings are in [`GLOSSARY.md`](../GLOSSARY.md), not restated here.

| Type | Lives in | Role |
|------|----------|------|
| `EffectConfig` | `effects/effect.py` | Resolution, options, and listeners for one render pass |
| `PixelBuffer` | `effects/effect.py` | List-backed in-memory pixel buffer of packed RGB values |
| `EffectVerb` | `effects/effect.py` | Identity-matched key for `clips` and `patterns`; engine owns `START`/`STOP`, `EffectPixels` subclasses declare custom verbs in `VERBS` |
| `Effect` | `effects/effect.py` | Descriptor of an effect's modalities (`pixels`, `audio`, `haptic`); builders return plain instances |
| `Layer` | `effects/layers/layer.py` | Base layer: `update` + `sample` |
| `Scroll` | `effects/layers/scroll.py` | Scroll base: `update` + `apply` |
| `LayerRenderer` | `effects/layers/renderer.py` | Single-layer `Effect` |
| `AddColorsRenderer` | `effects/layers/add_colors_renderer.py` | Composites layers by summing packed RGB colors |
| `AddSamplesRenderer` | `effects/layers/add_samples_renderer.py` | Composites layers by summing float samples then sampling a palette |
| `ProgressRenderer` | `effects/layers/progress_renderer.py` | Progress fill in one raw RGB color, no palette |
| `Palette` / `PaletteLUT256` | `effects/palette.py` | Maps float [0,1] → packed RGB; LUT variant is pre-computed |
| `Shape` | `effects/shape.py` | Factory for `EffectShapeFunc` callables (gradient, sine, checkers, …) |
| `EffectControls` | `engine/state.py` | Rule-facing effect seam |
| `EffectAdmin` | `engine/effects/admin.py` | Scene-transition seam, reserved for `SceneManager`: `enter_boot_scene`, `cover` (→ `HeldEffects`), `uncover`, each installing a `SceneView` |
| `SceneView` | `engine/effects/admin.py` | A scene's local effects, local sounds and declared effect-pack names: what each `EffectAdmin` step installs |
| `EffectManager` | `engine/effects/manager.py` | Concrete `EffectControls` + `EffectAdmin`; routes effects to outputs by scope |
| `EffectOutput` | `engine/effects/output.py` | Abstract hardware output port |
| `EffectBuilder` | `engine/effects/builder.py` | Callable `(name, config) → Effect`; one per effect item |
| `EffectReceipt` | `engine/state.py` | Handle for a running effect; `stop` plus `brightness`/`loudness` controls |
| `ScopeValue` / `Scope` | `engine/state.py` | Output-agnostic routing keys (see glossary) |
| `NetworkControls` | `engine/state.py` | Rule-facing send-only network seam; a send on missing hardware raises `MissingCapabilityError` |
| `ActiveSceneNamespace` | `engine/namespace.py` | Resolves effect names to builders and clip names to WAV paths for the active scene; its Scene view is installed by each `EffectAdmin` step |
| `ResolvedClip` | `effects/effect.py` | A declared `AudioPlaybackConfig` plus its resolved path, carried on `EffectEvent` |
| `GameState` | `engine/state.py` | Per-tick context passed to each rule: `get`/`set` game data, `queue_event`, the scene's own game time (`elapsed`/`total`), read-only `settings` and `capabilities`, and the control seams |
| `SceneRun` | `engine/state.py` | A scene's `GameState` plus its rules in dispatch order; the only dispatcher of the scene's queued events, via `tick(elapsed)` |
| `Capabilities` | `engine/capabilities.py` | Read-only view of the device's Capabilities that rules ask with `has(name)` |
| `Settings` | `engine/settings.py` | One scene's resolved Settings, read by namespace (`scene` or a Rule pack name) and name; built by the catalog scan |
| `GameRule` | `engine/engine.py` | Base rule: registers per-event-type handlers with `on`; `handle_event` routes by exact event class |
| `Scene` | `engine/scene.py` | One scene's read-only record, built once by the scan: pack references, version, `ir_codec`, resolved Settings, Required capabilities, scene-local registries and sounds |
| `SceneControls` | `engine/state.py` | Rule-facing transition seam (`overlay`, `pop`, `reboot_into`, `reboot_to_previous`; no in-process scene switch, see ADR-0005) plus `can_run(name)`, which the `lobby` pack asks to leave out entries the device can't play |
| `SceneManager` | `engine/scene.py` | The live `SceneControls`: keeps the scene stack of `SceneRun`s, ticks the top one, and drives each transition through one `EffectAdmin` call; reboots go through the injected `SceneReboot`. Transitions raise `MissingCapabilityError` before changing anything; `pop` does not check |
| `SceneRuntime` | `engine/scene_runtime.py` | The engine's matched set built from a `PackCatalog` and what the device offers: one `ActiveSceneNamespace`, the `EffectManager` and the `SceneManager`, on one clock it advances once per tick (`advance_clock()`, then `queue_event`, then `update()`); exposes only `scene_controls` and `namespace` |
| `SceneReboot` | `engine/state.py` | Board-free port `SceneManager` reboots through; `previous_scene()` names the scene `reboot_to_previous` would boot, so it is checked first; live adapter `DeviceSceneReboot` |
| `PhaseKey` / `PhaseMachine` | `engine/phase.py` | Identity-typed phase constant; per-scene current-phase holder |
| `PhaseSlot` | `engine/phase.py` | Per-scene typed accessor for a phase machine's key + initial phase; registry of each phase's owning `PhaseRule` |
| `PhaseRule` / `InPhaseRule` | `engine/phase.py` | Phase-owning rule (lifecycle + transitions) vs. phase-gated reactor |
| `MergeStrategy` | `engine/state.py` | Per-scope compositing policy; subclasses in `engine/effects/merge.py` |
| `PackRegistry` | `engine/packs.py` | Looks up the items of versioned effect or rule packs by pack and item name; filled only by the catalog |
| `PackCatalog` | `engine/pack_catalog.py` | One scan of every pack root: effect/rule `PackRegistry`s, `SceneRegistry`, pack sounds map; scene declarations, Setting overrides and `requires` names checked, Settings resolved |
| `SceneRegistry` | `engine/scene.py` | Built from a mapping of scene names to `Scene` records; `get` returns the stored record, and every other question (`ir_codec_for`, `required_capabilities`, `names`, `resolve_known`) reads that one mapping |
| `UnknownCapabilityError` / `MissingCapabilityError` | `engine/capabilities.py` | The Capability errors: a `requires` name outside the vocabulary (a `PackScanError`), and a device lacking what a scene or send needs (raised at boot when neither the Persisted scene nor `default_scene` fits, and by a transition into a scene the device can't run) |
| `Event` / `EventGroup` | `engine/events.py` | Named events grouped by category |
| `Timer` | `engine/timer.py` | Per-tick elapsed/cumulative time tracker |
| `Aura` | `magic/aura.py` | A player/object's magic pool + active `Spells` collection |
| `Spell` | `magic/aura.py` | Base class for spells; `update` returns `True` to self-remove |
| `Spells` | `magic/aura.py` | Collection with lookup by name, tag, or class |
| `AuraEvent` | `magic/aura.py` | Base event routed through active spells; can be canceled |
| `MinMaxValue` | `magic/values.py` | Clamped float with dynamic max (via `ValueWithModifiers`) |
| `ValueWithModifiers` | `magic/values.py` | Base value + temporary multiplier stack |
| `Duration` | `magic/values.py` | Expiry tracker |
| `DeviceConfig` | `hardware/shared/device_config.py` | Validated `aura-device.json`: optional `pixels` list, IR/audio/sensor/haptics/radio/SD sections and **Named bus** maps; every pin is recorded as a `PinRef` |
| `PinRef` | `hardware/shared/device_config.py` | **Pin reference**: a pin name with the `aura-device.json` field it came from, so a pin error names the field to fix; lives with the config so the parser can create it without importing `DeviceParts` |
| `NeoPixelCurrentBudgetConfig` | `hardware/shared/device_config.py` | Opt-in `neopixel_current_budget` policy; parsing folds the tuned brightness (`hardware/shared/neopixel_current_budget.py`) into each NeoPixel strip config |
| `DeviceHardware` | `hardware/shared/device_hardware.py` | Board-free bundle the Device assembly returns: outputs, sensors, network seam, `ir`, radio, storage, the `capabilities` it built, and its ordered **Polled parts** (`polled`) |
| `assemble_device` | `hardware/shared/device_assembly.py` | The **Device assembly**: board-free `DeviceConfig` → `DeviceHardware` (gating, bus opening, build order, **Boot narration** over `hardware/shared/build_narration.py`, IR/radio wiring); reaches hardware only through `DeviceParts` |
| `DeviceParts` | `hardware/shared/device_parts.py` | Port the Device assembly builds each part through; adapters `CircuitPythonParts` (`hardware/circuitpython/circuitpython_parts.py`) and `SimulatedParts` (`hardware/simulated/simulated_parts.py`) |
| `PolledSensor` | `hardware/shared/polled_sensor.py` | **Polled part** owning one sensor's reading, updated in place each tick; keeps the last good reading on a failed read |
| `HardwareNetworkControls` | `hardware/shared/network_controls.py` | Concrete, send-only `NetworkControls` adapter; `send_ir` raises `MissingCapabilityError` when IR or the emitter is absent, `send_radio` when the radio is |
| `InfraredTransceiver` | `hardware/shared/ir_transceiver.py` | Board-free single owner of the IR subsystem: transmitters, an optional receiver and the shared transmit gate, on the device and the Simulated device alike |
| `RadioTransport` | `hardware/shared/radio_transport.py` | Board-free half-duplex radio port; live adapter `Rfm69RadioTransport` |
| `RadioTransceiver` | `hardware/shared/radio_transceiver.py` | Board-free single owner of a device's radio subsystem |
| `build_scene_boot` | `app/scene_composition.py` | The **Scene boot**, the Composition layer's only entry point: boots a `DeviceHardware` into its boot scene and returns a `SceneBoot`; shared by `run_scene` and the Simulated device |
| `SceneBoot` | `app/scene_composition.py` | What `build_scene_boot` returns: the booted `scene_name`, its `tick`, `scene_controls` and `namespace`. The tick advances the runtime clock, updates every **Polled part**, queues their events and updates the runtime; it allocates nothing per tick |
| `DeviceSceneReboot` | `hardware/shared/device_reboot.py` | Live `SceneReboot` adapter; persists the target, then calls its injected `reset` (`build_scene_boot` wires it; `run_scene` passes `microcontroller.reset`) |
| `SdSyncServer` | `hardware/shared/sd_sync_server.py` | Board-free device side of the SD-sync protocol |
| `SdSyncClient` | `scripts/sd_sync_client.py` | Board-free (CPython-only) host side of the SD-sync protocol |
| `Transport` (SD sync) | `hardware/shared/sd_sync_protocol.py` | Board-free port `SdSyncClient`/`SdSyncServer` exchange base64-framed lines through; live adapters `UsbCdcTransport` (device) / `SerialTransport` (host) |
| `UsbCdcTransport` | `hardware/circuitpython/usb_cdc_transport.py` | Live `Transport` framing SD-sync lines with a newline delimiter over any `read`/`write` stream (on-device, `usb_cdc.data`); needs no `usb_cdc` import itself, so it is CPython-testable against a fake stream |
| `SerialTransport` | `scripts/sd_sync_transport.py` | Live host-side `Transport`, framing SD-sync lines the same way as `UsbCdcTransport` but over a host serial port opened via `deploy_watch`'s `SerialHandle`/`_open_serial_with_retry` |
| `find_data_port` / `select_data_port` | `scripts/sd_sync_transport.py` | Data-channel **Port auto-detect** for `scripts/sd_sync.py`; `--port` overrides |
| `find_console_port` / `select_console_port` | `scripts/deploy_watch.py` | Console-channel **Port auto-detect** for `deploy_watch`; `--port` overrides |
| `ship_list` / `ShipList` / `ShipEntry` / `governed_mount_files` | `scripts/ship_list.py` | The **Ship list**: which files land where on a device (`MODULE_DIRS`, exclusions, compiled or raw, `boot.py` placement). `scripts/build.py` stages it; `scripts/deploy.py` syncs it and prunes mount files it no longer names |

---

## Domain vocabulary

Code-facing terms are defined in [`GLOSSARY.md`](../GLOSSARY.md) — the single source for the project's vocabulary and the words to avoid. Magic-system vocabulary (elements, auras, spells) lives in the aura-docs vault (`Overview/Magic System.md`).

---

## Coding constraints (CircuitPython and MicroPython compatibility)

All code that ships to a device (`effects/`, `engine/`, `magic/`, `packs/`, `hardware/shared/`, `app/`; see the **Ship list**) must run on CPython, CircuitPython 10.x, and MicroPython; only `hardware/circuitpython/` and `app/run_scene.py` may import CircuitPython-only modules. The general CircuitPython/MicroPython rules (no `dataclasses`, `typing.Protocol` unavailable, guarded `typing` imports, no per-frame hot-path allocation) live in the **code-quality skill's embedded-python guidance** (the `embedded-python.md` reference file) — follow it. If that skill isn't installed locally, look it up and copy that file's rules before working on device code. Project-specific deltas on top:

- **`typing.Protocol` substitute** — use plain base classes with `raise NotImplementedError`; subclass explicitly for type-checker compatibility
- **`PaletteLUT256` is pre-computed** — never construct inside a render loop
- **Line limit: 100 characters** — enforced by `ruff` pre-commit hook (also `ruff format`)

`scripts/` is CPython-only and does not carry these constraints.

---

## Tests

Over 3,000 tests, in `tests/` folders beside the code they cover. Run with `uv run pytest`. All must pass before commit. Pre-commit hooks run `ruff` (lint), `ruff format`, `import-linter` and `mypy`.
