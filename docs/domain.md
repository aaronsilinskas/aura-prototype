# Domain: aura-prototype

## What this project is

`aura-prototype` is the Python/CircuitPython/MicroPython animation and game-logic engine for the **Aura** live-action game platform. Aura is a physical magic game played with custom props (wands, targets, tokens) powered by microcontrollers.

This repo implements:
- A composable LED animation engine (`effects/`) that runs on both CPython and CircuitPython
- Game rules for a magic system built around ten elements (Fire, Water, Earth, Ice, Air, Lightning, Light, Dark, Time, Gravity)
- An event-driven game engine (`engine/`)
- Spell and aura logic (`magic/`)

Full game and hardware design lives in `~/dev/aura/aura-docs/`, the maintainer's private Obsidian vault (contributors won't have it). Key references for agents that do:
- `Overview/Magic System.md` — element definitions, buffs/debuffs, spell mechanics
- `Overview/Design Principles.md` — core game design goals
- `Reference/Props and Hardware.md` — physical device inventory

---

## Module layout

```
effects/          Animation engine (CircuitPython-safe)
  effect.py       Effect and its modalities, effect config and verbs, clip and haptic values
  palette.py      Palettes
  shape.py        Shape functions
  level.py        The **Effect Level**'s range and its one read
  value.py        Dynamic values and generators
  layers/         **Layer** base class, the layers and the **Renderers**

engine/           Event-driven game loop (CircuitPython/MicroPython-safe)
  engine.py       GameRule
  state.py        GameState, the rule-facing seams, scopes and merge-strategy base
  scene.py        Scene records, registries and SceneManager
  scene_runtime.py SceneRuntime, built from a PackCatalog
  phase.py        Phase keys, machine, slots and rules
  events.py       Events and event groups
  timer.py        Timer
  lerp.py         The one level interpolation, for Game and Effect Levels
  packs.py        Pack registries and the lookup-time error family
  pack_catalog.py The pack scan, PackCatalog and the scan-time error family
  scan_error.py   PackScanError base, kept apart so capabilities.py stays importable by hardware
  capabilities.py Capability vocabulary, the Capabilities view and the Capability errors
  settings.py     Settings view, Setting declaration parsing and resolution
  version.py      Pack MAJOR.MINOR parsing
  input.py        Input readings and input events
  namespace.py    The **Active scene namespace** and its name-resolution errors
  network.py      Network events and the IR emitter vocabulary
  log.py          Board-free, tag-prefixed line logger with an injectable sink
  effects/
    admin.py      EffectAdmin and SceneView (the scene-transition face; hardware can't reach it)
    builder.py    Effect builders
    manager.py    EffectManager
    output.py     EffectOutput, the abstract hardware output port
    merge.py      The two merge strategies

magic/            Spell and aura game logic (CircuitPython/MicroPython-safe)
  aura.py         Auras, spells and aura events
  caster.py       Casters and cast types
  values.py       Modifiable values, durations and counters
  spell/          Individual spell implementations

packs/            Game-specific packs loaded at runtime (CircuitPython/MicroPython-safe)
  effects/        Shared, versioned effect packs (basic, elements) — each with an effects.json manifest
  rules/          Shared, versioned rule packs, each with a rules.json manifest
  scenes/         Scene definitions; each has a scene.json and optional scene-local
                  effects/, rules/ and sounds/ subdirs

hardware/         Hardware abstraction layer
  circuitpython/  CircuitPython drivers and the device-only entry point that runs the
                  **Device assembly** (device_builder)
  shared/         Hardware-agnostic, board-free parts: the Device assembly, device config,
                  storage and state, IR and radio subsystems, SD-sync protocol
  simulated/      Test-only **Simulated device** and its `DeviceParts` adapter; never deployed

app/              Composition layer — the one place allowed to import both the engine's
                  runtime machinery and hardware.* together
  scene_composition.py  The **Scene boot**, board-free and CPython-testable; shared by
                        the device and the **Simulated device**
  run_scene.py          The device-only entry point: bring-up, then the boot's tick in a loop
  simulation/           Test-only **Simulation test harness**; never deployed

examples/         Runnable CircuitPython entry points; deploy-watch's flash targets

scripts/          Deploy and maintenance scripts (CPython-only)

typings/          Local type stubs for device-only driver libraries, read by mypy

electronics/      PCB design source (KiCad), not Python; outside the module layering below
```

### Module layering

The `engine` ↔ `hardware` boundary is one-way and enforced by `import-linter`
(`[tool.importlinter]` in `pyproject.toml`, run via the `lint-imports`
pre-commit hook on every commit):

- `engine` must never import `hardware` or `app` (total, one-way).
- `hardware` must never import engine runtime machinery — `engine.engine`,
  `engine.scene`, `engine.scene_runtime`, `engine.packs`, `engine.namespace`,
  `engine.timer`, `engine.effects.admin`, `engine.effects.manager`. Hardware never resolves effect or clip names; it
  plays the path on each event's resolved clip (ADR-0002).
- `app/` is the sole sanctioned crossing point: the one place allowed to
  import both the engine's runtime machinery and `hardware.*` together (see
  **Composition layer (app/)** in `GLOSSARY.md`).
- No shipped module may import the test-only `app.simulation` or
  `hardware.simulated`; only `tests/` packages may. The **Ship list**
  (`scripts/ship_list.py`) leaves both directories out, so they never
  reach a device.
- The **Scene boot** (`app.scene_composition`) must not import
  `hardware.circuitpython` or the CircuitPython-only modules that package
  imports (`board`, `microcontroller`, the `adafruit_*` drivers and others),
  even indirectly: it also boots the **Simulated device** under CPython.
- No device package (`effects`, `engine`, `magic`, `packs`, `hardware`, `app`)
  may import `scripts`, which is CPython-only and never ships.

---

## Key types and relationships

A map of where the major types live. Authoritative term meanings are in [`GLOSSARY.md`](../GLOSSARY.md), not restated here.

| Type | Lives in | Role |
|------|----------|------|
| `EffectConfig` | `effects/effect.py` | Resolution, options, and listeners for one render pass |
| `PixelBuffer` | `effects/effect.py` | List-backed in-memory pixel buffer of packed RGB values |
| `EffectVerb` | `effects/effect.py` | Identity-matched key for `clips` and `patterns`; engine owns `START`/`STOP`, `EffectPixels` subclasses declare custom verbs in `VERBS` |
| `Effect` | `effects/effect.py` | Descriptor of an effect's modalities (`pixels`, `audio`, `haptic`); builders return plain instances |
| `Layer` | `effects/layers/layer.py` | Base class of every **Layer** |
| `Scroll` | `effects/layers/scroll.py` | Base class of the position scroll helpers |
| `LayerRenderer` | `effects/layers/renderer.py` | Single-layer `Effect` |
| `AddColorsRenderer` | `effects/layers/add_colors_renderer.py` | Composites layers by summing packed RGB colors |
| `AddSamplesRenderer` | `effects/layers/add_samples_renderer.py` | Composites layers by summing float samples then sampling a palette |
| `ProgressRenderer` | `effects/layers/progress_renderer.py` | Progress fill in one raw RGB color, no palette |
| `Palette` / `PaletteLUT256` | `effects/palette.py` | Maps float [0,1] → packed RGB; LUT variant is pre-computed |
| `Shape` | `effects/shape.py` | Factory for `EffectShapeFunc` callables (gradient, sine, checkers, …) |
| `EffectControls` | `engine/state.py` | Rule-facing effect seam |
| `EffectAdmin` | `engine/effects/admin.py` | Scene-transition seam, reserved for `SceneManager` |
| `SceneView` | `engine/effects/admin.py` | The **Scene view** each `EffectAdmin` step installs |
| `EffectManager` | `engine/effects/manager.py` | Concrete `EffectControls` + `EffectAdmin`; routes effects to outputs by scope |
| `EffectOutput` | `engine/effects/output.py` | Abstract hardware output port |
| `EffectBuilder` | `engine/effects/builder.py` | Builds one effect item's `Effect`; each effect item exports one as `BUILD` |
| `ComposedEffectBuilder` | `engine/effects/builder.py` | `EffectBuilder` that composes a base effect's pixels with declared audio and haptic |
| `EffectReceipt` | `engine/state.py` | Handle for a running effect; `stop` plus `brightness`/`loudness` controls |
| `ScopeValue` / `Scope` | `engine/state.py` | Output-agnostic routing keys (see glossary) |
| `NetworkControls` | `engine/state.py` | Rule-facing send-only network seam; a send on missing hardware raises `MissingCapabilityError` |
| `ActiveSceneNamespace` | `engine/namespace.py` | The **Active scene namespace** |
| `ResolvedClip` | `effects/effect.py` | A declared `AudioPlaybackConfig` plus its resolved path, carried on `EffectEvent` |
| `GameState` | `engine/state.py` | Per-tick context passed to each rule |
| `SceneRun` | `engine/state.py` | One run of a scene: its `GameState` and rules; the only dispatcher of the scene's queued events |
| `Capabilities` | `engine/capabilities.py` | Read-only view of the device's **Capabilities** that rules ask |
| `Settings` | `engine/settings.py` | One scene's resolved **Settings**, built by the catalog scan |
| `GameRule` | `engine/engine.py` | Base class of every rule; handles each event by its exact class |
| `Scene` | `engine/scene.py` | One scene's read-only record, built once by the scan |
| `SceneControls` | `engine/state.py` | Rule-facing scene-transition seam (ADR-0005) |
| `SceneManager` | `engine/scene.py` | The live `SceneControls`: owns the scene stack and drives each transition |
| `SceneRuntime` | `engine/scene_runtime.py` | The **SceneRuntime**: the namespace, `EffectManager` and `SceneManager` as one matched set |
| `SceneReboot` | `engine/state.py` | Board-free port `SceneManager` reboots through; live adapter `DeviceSceneReboot` |
| `PhaseKey` / `PhaseMachine` | `engine/phase.py` | Identity-typed phase constant; per-scene current-phase holder |
| `PhaseSlot` | `engine/phase.py` | Per-scene accessor for a phase machine; registry of each phase's owning `PhaseRule` |
| `PhaseRule` / `InPhaseRule` | `engine/phase.py` | Phase-owning rule vs. phase-gated reactor |
| `MergeStrategy` | `engine/state.py` | Per-scope compositing policy; subclasses in `engine/effects/merge.py` |
| `PackRegistry` | `engine/packs.py` | Looks up the items of versioned effect or rule packs by pack and item name; filled only by the catalog |
| `PackCatalog` | `engine/pack_catalog.py` | The **PackCatalog**: the product of one scan of every **Pack root** |
| `SceneRegistry` | `engine/scene.py` | The installed `Scene` records, keyed by name |
| `UnknownCapabilityError` / `MissingCapabilityError` | `engine/capabilities.py` | The **Capability errors** |
| `Event` / `EventGroup` | `engine/events.py` | Named events grouped by category |
| `Timer` | `engine/timer.py` | Per-tick elapsed/cumulative time tracker |
| `Aura` | `magic/aura.py` | A player/object's magic pool + active `Spells` collection |
| `Spell` | `magic/aura.py` | Base class for spells |
| `Spells` | `magic/aura.py` | Collection with lookup by name, tag, or class |
| `AuraEvent` | `magic/aura.py` | Base event routed through active spells; can be canceled |
| `MinMaxValue` | `magic/values.py` | Clamped float with dynamic max (via `ValueWithModifiers`) |
| `ValueWithModifiers` | `magic/values.py` | Base value + temporary multiplier stack |
| `Duration` | `magic/values.py` | Expiry tracker |
| `DeviceConfig` | `hardware/shared/device_config.py` | The validated `aura-device.json`; every pin in it is a `PinRef` |
| `PinRef` | `hardware/shared/device_config.py` | The **Pin reference**; lives with the config so the parser can create it without importing `DeviceParts` |
| `NeoPixelCurrentBudgetConfig` | `hardware/shared/device_config.py` | The `neopixel_current_budget` policy; its math lives in `hardware/shared/neopixel_current_budget.py` |
| `DeviceHardware` | `hardware/shared/device_hardware.py` | Board-free bundle the **Device assembly** returns |
| `assemble_device` | `hardware/shared/device_assembly.py` | The **Device assembly**; reaches hardware only through `DeviceParts` |
| `DeviceParts` | `hardware/shared/device_parts.py` | Port the Device assembly builds each part through; adapters `CircuitPythonParts` (`hardware/circuitpython/circuitpython_parts.py`) and `SimulatedParts` (`hardware/simulated/simulated_parts.py`) |
| `PolledSensor` | `hardware/shared/polled_sensor.py` | The **PolledSensor** |
| `HardwareNetworkControls` | `hardware/shared/network_controls.py` | Concrete, send-only `NetworkControls` adapter |
| `InfraredTransceiver` | `hardware/shared/ir_transceiver.py` | The **InfraredTransceiver** |
| `RadioTransport` | `hardware/shared/radio_transport.py` | Board-free half-duplex **Radio** port, one for both directions; live adapter `Rfm69RadioTransport` |
| `Rfm69RadioTransport` | `hardware/circuitpython/rfm69_radio_transport.py` | Live `RadioTransport` over the RFM69 driver |
| `RadioTransceiver` | `hardware/shared/radio_transceiver.py` | Board-free owner of a device's whole **Radio** subsystem, exposed as `DeviceHardware.radio` |
| `build_scene_boot` | `app/scene_composition.py` | The **Scene boot**, the Composition layer's only entry point; shared by `run_scene` and the Simulated device |
| `SceneBoot` | `app/scene_composition.py` | What `build_scene_boot` returns, including the booted scene's `tick` |
| `DeviceSceneReboot` | `hardware/shared/device_reboot.py` | Live `SceneReboot` adapter, wired by `build_scene_boot` |
| `PersistedScene` | `hardware/shared/persisted_scene.py` | Board-free owner of the **Persisted scene** record; a client of the boot's one `DeviceStateStore` (ADR-0009) |
| `DeviceStateStore` | `hardware/shared/device_state.py` | Board-free, general key/value store over the card's `aura-state.json` (ADR-0009) |
| `SdSyncServer` | `hardware/shared/sd_sync_server.py` | Board-free device side of the SD-sync protocol (ADR-0011) |
| `SdSyncClient` | `scripts/sd_sync_client.py` | Board-free (CPython-only) host side of the SD-sync protocol (ADR-0011) |
| `Transport` (SD sync) | `hardware/shared/sd_sync_protocol.py` | Board-free port `SdSyncClient`/`SdSyncServer` exchange base64-framed lines through (ADR-0011); live adapters `UsbCdcTransport` (device) / `SerialTransport` (host) |
| `LineFramer` | `hardware/shared/sd_sync_protocol.py` | Splits a byte stream into SD-sync frame lines; both live transports frame through it |
| `UsbCdcTransport` | `hardware/circuitpython/usb_cdc_transport.py` | Live device-side `Transport`; imports no `usb_cdc`, so it is CPython-testable |
| `SerialTransport` | `scripts/sd_sync_transport.py` | Live host-side `Transport` over a host serial port |
| `find_port` / `SerialChannel` / `PortAutoDetectError` | `scripts/port_auto_detect.py` | **Port auto-detect** |
| `ship_list` / `ShipList` / `ShipEntry` / `governed_mount_files` | `scripts/ship_list.py` | The **Ship list**; `scripts/build.py` stages it and `scripts/deploy.py` syncs it |
| `plan_deploy` / `DeployPlan` / `CompiledBuild` / `SourceBuild` / `execute_plan` | `scripts/deploy.py` | The deploy in two steps: `plan_deploy` returns the **Deploy plan**, and `execute_plan` carries it out; `run_deploy_cli` is the command-line adapter shared by `main` and deploy-watch |
| `DeployError` | `scripts/deploy.py` | Raised when a deploy is refused or fails |
| `Toolchain` / `MpyCross` | `scripts/build.py` | Port (ADR-0012) for compiling device modules to `.mpy`; `MpyCross` is the real binary |

---

## Domain vocabulary

Code-facing terms are defined in [`GLOSSARY.md`](../GLOSSARY.md) — the single source for the project's vocabulary and the words to avoid. Magic-system vocabulary (elements, auras, spells) lives in the aura-docs vault (`Overview/Magic System.md`).

---

## Coding constraints (CircuitPython and MicroPython compatibility)

All code that ships to a device (`effects/`, `engine/`, `magic/`, `packs/`, `hardware/shared/`, `app/`; see the **Ship list**) must run on CPython, CircuitPython 10.x, and MicroPython; only `hardware/circuitpython/` and `app/run_scene.py` may import CircuitPython-only modules. The general CircuitPython/MicroPython rules (no `dataclasses`, `typing.Protocol` unavailable, guarded `typing` imports, no per-frame hot-path allocation) live in the **`embedded-python` skill** — follow it. If that skill isn't installed locally, look it up and copy its rules before working on device code. Project-specific deltas on top:

- **`typing.Protocol` substitute** — use plain base classes with `raise NotImplementedError`; subclass explicitly for type-checker compatibility (ADR-0012)
- **`PaletteLUT256` is pre-computed** — never construct inside a render loop
- **Line limit: 100 characters** — enforced by `ruff` pre-commit hook (also `ruff format`)

`scripts/` is CPython-only and does not carry these constraints.

---

## Design constraints

Rules an agent must not break, in every package, `scripts/` included.

- **Rules are Game-data-stateless** — a `GameRule` keeps all game data in `GameState`; construction-time config is its only instance state (`engine/engine.py`, `packs/`)
- **One clock** — only `SceneRuntime.advance_clock` advances the **Timer**, once per tick; rules read time through `GameState` (`engine/timer.py`, `engine/scene_runtime.py`)
- **The Tag protocol is immutable** — never change its timings or add a CRC; it is a compatibility contract with non-Aura hardware (`hardware/shared/ir_codecs/tag.py`)
- **One Reboot path between scenes** — rules never load a scene in-process (`engine/scene.py`, ADR-0005)
- **SD sync has one wire format** — both ends frame lines through `hardware/shared/sd_sync_protocol.py`, so a change reaches the device and the host at once; one protocol test pins the bytes, and other SD-sync tests assert only what moved (ADR-0011)
- **Routine SD-sync failures are replies** — `SdSyncServer` answers "not found" and "no SD configured" in-band, never by raising; `SdSyncClient` surfaces them as typed errors (ADR-0011)
- **`usb_cdc` stays in device-only wiring** — only `hardware/circuitpython/boot.py` and `examples/sd_sync.py` import it, so `UsbCdcTransport` stays CPython-testable
- **Host SD sync reads only the Data channel** — `SerialTransport` frames bytes there; deploy-watch's UTF-8 line reader is for the **Console channel** (`scripts/sd_sync_transport.py`, `scripts/deploy_watch.py`)
- **Port auto-detect never guesses** — no match, or more than one, fails; it never falls back to the only serial device (`scripts/port_auto_detect.py`)
- **Hardware builds no game events** — IR and radio deliver bytes; only the **Scene boot**'s tick turns them into `NetworkEvents` (`app/scene_composition.py`, `hardware/shared/`)
- **Driver libraries load in their part** — each per-component driver library, and an adapter that imports one (`Rfm69RadioTransport`, `SdCardStorage`), is imported only inside the `CircuitPythonParts` part that builds it (`hardware/circuitpython/`, ADR-0013)

---

## Tests

Tests live in `tests/` folders beside the code they cover. Run with `uv run pytest`, or the full check (hooks, then tests) with `bash scripts/check.sh`. All must pass before commit. `.pre-commit-config.yaml` lists the pre-commit hooks.
