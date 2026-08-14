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
                  AudioPlaybackConfig, HapticPattern
  palette.py      Palette, PaletteLUT256 (pre-computed, immutable)
  shape.py        Shape (factory), EffectShapeFunc
  level.py        clamp_level, level_progress, level_lerp, level_lerp_int
  value.py        DynamicValue, ValueGenerator, lerp
  performance.py  PerformanceTracker
  layers/         Layer base class + scroll, flame, drift_noise, sparkle, shape, progress, pulse
                  layers and the renderer compositors

engine/           Event-driven game loop (CircuitPython/MicroPython-safe)
  engine.py       GameEngine, GameRule
  state.py        GameState, EffectControls, EffectAdmin, EffectReceipt, MergeStrategy,
                  NetworkControls, Scope, ScopeValue
  scene.py        Scene, SceneRegistry, SceneLocalRegistry, SceneManager, SceneControls
  phase.py        PhaseKey, PhaseMachine, PhaseSlot, PhaseRule, InPhaseRule
  events.py       Event, EventGroup, EffectEvent
  timer.py        Timer
  lerp.py         Integer/float interpolation helpers
  packs.py        PackRegistry
  version.py      Pack semver parsing and comparison
  input.py        ButtonData, AccelerationData, InputEvents
  audio.py        AudioRegistry
  network.py      NetworkEvents, TransmitPump
  effects/
    manager.py    EffectManager, EffectBuilder, EffectResolver
    output.py     EffectOutput (abstract hardware output port)
    merge.py      SplitMerge, AdditiveMerge (per-scope layered-buffer compositing;
                  subclass state.py's MergeStrategy)

magic/            Spell and aura game logic (CircuitPython/MicroPython-safe)
  aura.py         Aura, Spell, Spells, SpellTags, SpellLevelScaler, AuraEvent (+ subclasses), EventListener
  caster.py       Caster, CastType (LINE / CONE / AREA_OF_EFFECT)
  values.py       MinMaxValue, ValueWithModifiers, ValueModifier, ValueModifiers, Duration, Counter
  spell/          Individual spell implementations (elemental/, combo/, ambient_magic_regen)

packs/            Game-specific packs loaded at runtime (CircuitPython/MicroPython-safe)
  effects/        Shared, versioned effect packs (basic, elements) — each with a version.txt
  rules/          Shared, versioned rule packs (debug)
  scenes/         Scene definitions (element_browser, hardware_test, red_light_green_light, tag);
                  each has a scene.json and optional scene-local effects/ and rules/ subdirs

hardware/         Hardware abstraction layer
  circuitpython/  CircuitPython drivers (device_builder, is31fl3741_output, drv2605_output,
                  neopixel_output, audio_output, infrared_io, pio_pulse_writer,
                  counting_i2c, rfm69_radio_transport)
  shared/         Hardware-agnostic helpers (matrix_output, voice_pool, debounced_buttons,
                  device_config, device_hardware, network_controls, scene_selection,
                  ir_transport, ir_protocol, tag_protocol, ir_telemetry, ir_manager,
                  radio_transport, radio_manager, profiler_report)

app/              Composition layer — the one place allowed to import both the engine's
                  runtime machinery and hardware.* together
  scene_composition.py  build_scene_runtime (board-free, CPython-testable)
  scene_runtime.py      run_scene (device-only)

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
  `engine.scene`, `engine.packs`, `engine.timer`, `engine.effects.manager`.
- `app/` is the sole sanctioned crossing point: the one place allowed to
  import both the engine's runtime machinery and `hardware.*` together (see
  **Composition layer (app/)** in `domain-language.md`).

---

## Key types and relationships

A map of where the major types live. Authoritative term meanings are in [`domain-language.md`](domain-language.md), not restated here.

| Type | Lives in | Role |
|------|----------|------|
| `EffectConfig` | `effects/effect.py` | Resolution, options, and listeners for one render pass |
| `PixelBuffer` | `effects/effect.py` | List-backed in-memory pixel buffer of packed RGB values |
| `Effect` | `effects/effect.py` | Base class for all effects; subclasses implement `name`, `update(elapsed)`, `render(output)` |
| `Layer` | `effects/layers/layer.py` | Base layer: `update(elapsed)` + `sample(position, pixel_count) -> float` |
| `Scroll` | `effects/layers/scroll.py` | Scroll base: `update(elapsed)` + `apply(position) -> float` |
| `LayerRenderer` | `effects/layers/renderer.py` | Single-layer `Effect` |
| `AddColorsRenderer` | `effects/layers/add_colors_renderer.py` | Composites layers by summing packed RGB colors |
| `AddSamplesRenderer` | `effects/layers/add_samples_renderer.py` | Composites layers by summing float samples then sampling a palette |
| `Palette` / `PaletteLUT256` | `effects/palette.py` | Maps float [0,1] → packed RGB; LUT variant is pre-computed |
| `Shape` | `effects/shape.py` | Factory for `EffectShapeFunc` callables (gradient, sine, checkers, …) |
| `EffectControls` | `engine/state.py` | Rule-facing abstract interface: `set_effect`, `add_effect`, `stop_effect`, `set_merge_strategy` |
| `EffectAdmin` | `engine/state.py` | Scene-transition-facing abstract interface, reserved for `SceneManager`: `reset_merge_strategies`, `capture_merge_strategies`, `apply_merge_strategies`, `set_local_effects`, `set_allowed_packs` |
| `EffectManager` | `engine/effects/manager.py` | Concrete `EffectControls` + `EffectAdmin` — two faces of one instance, mirroring `NetworkControls`/`TransmitPump`; routes effects to outputs by scope |
| `EffectOutput` | `engine/effects/output.py` | Abstract hardware output: `create_buffer`, `update_pixels`, `handle_event` |
| `EffectBuilder` | `engine/effects/manager.py` | Callable `(name, config) → Effect`; one per effect pack |
| `EffectReceipt` | `engine/state.py` | Identity + `stop()` handle for a running effect instance; also carries validating `brightness`/`loudness` runtime controls in `[0.0, 1.0]` |
| `ScopeValue` / `Scope` | `engine/state.py` | Routing keys: `PERSONAL`, `DIRECTIONAL`, `AMBIENT`, `Global.MAIN/BUFF/DEBUFF`, and composites `Global.ALL` / `NON_AMBIENT` / `Scope.ALL` |
| `NetworkControls` | `engine/state.py` | Abstract interface for sending/receiving network messages |
| `TransmitPump` | `engine/network.py` | Abstract runtime-facing seam declaring `poll_transmits()`; the type the runtime loop reaches through, distinct from the send-only `NetworkControls` |
| `AudioOverlayAdmin` | `engine/audio.py` | Scene-transition-facing abstract interface, reserved for `SceneManager`: `set_scene_sounds(sounds \| None)`, `set_allowed_packs(names \| None)` |
| `AudioRegistry` | `engine/audio.py` | Concrete `AudioOverlayAdmin`; resolves a qualified clip name to a WAV path via prefix routing (`scene.` → active scene overlay, `<pack>.` → shared base scanned by `scan_pack_sounds`, gated by the `pack.` membership rule), raising on an unprefixed, undeclared-pack, or unresolved name |
| `GameEngine` | `engine/engine.py` | Event queue + `GameRule` list; driven by a single `update(timer)` tick |
| `GameState` | `engine/state.py` | Passed to each rule: holds `engine`, `timer`, `effect_controls`, `network_controls` |
| `GameRule` | `engine/engine.py` | Abstract event handler with `name` + `version` |
| `Scene` | `engine/scene.py` | Named game mode with its own effect and rule registries |
| `SceneManager` | `engine/scene.py` | Activates/deactivates scenes; owns `SceneLocalRegistry` per scene; holds injected `EffectAdmin` and `AudioOverlayAdmin` handles and drives every local-effects/merge-strategy/sound-overlay transition through them |
| `PhaseKey` / `PhaseMachine` | `engine/phase.py` | Identity-typed phase constant; per-scene current-phase holder |
| `PhaseSlot` | `engine/phase.py` | Per-scene typed accessor owning a phase machine's `GameState` key + initial phase; the one object all of a scene's phase rules and its module-level phase reference share |
| `PhaseRule` / `InPhaseRule` | `engine/phase.py` | Phase-owning rule (lifecycle + transitions) vs. phase-gated reactor |
| `EffectResolver` | `engine/effects/manager.py` | Resolves a qualified effect name to a builder; owns the `scene.` prefix rule |
| `MergeStrategy` | `engine/state.py` | Per-scope policy compositing a scope's layered effect buffers into one region buffer (subclasses `SplitMerge` / `AdditiveMerge` live in `engine/effects/merge.py`) |
| `PackRegistry` | `engine/packs.py` | Loads and looks up named packs (effects, rules, scenes) by entry point |
| `Event` / `EventGroup` | `engine/events.py` | Named events grouped by category |
| `Timer` | `engine/timer.py` | Per-tick elapsed/cumulative time tracker |
| `Aura` | `magic/aura.py` | A player/object's magic pool + active `Spells` collection |
| `Spell` | `magic/aura.py` | Base class for spells; `update` returns `True` to self-remove |
| `Spells` | `magic/aura.py` | Collection with lookup by name, tag, or class |
| `AuraEvent` | `magic/aura.py` | Base event routed through active spells; can be canceled |
| `MinMaxValue` | `magic/values.py` | Clamped float with dynamic max (via `ValueWithModifiers`) |
| `ValueWithModifiers` | `magic/values.py` | Base value + temporary multiplier stack |
| `Duration` | `magic/values.py` | Expiry tracker: `update(elapsed) → bool` |
| `DeviceConfig` | `hardware/shared/device_config.py` | Validated `aura-device.json`; `pixels` is an optional (possibly empty) list of `MatrixPixelsConfig` / `NeoPixelPixelsConfig`; optional `ir` / `audio` / `i2c` (`I2CConfig`) / `accelerometer` / `magnetometer` / `haptics` (each a shared `I2CDeviceConfig`) sections |
| `DeviceHardware` | `hardware/shared/device_hardware.py` | Named bundle `build_hardware` returns (outputs, buttons, network_controls, transmit_pump, …); board-free, importable under CPython |
| `HardwareNetworkControls` | `hardware/shared/network_controls.py` | Concrete `(NetworkControls, TransmitPump)` adapter over wired `InfraredTransmitter`s; constructed by `device_builder` |
| `InfraredManager` | `hardware/shared/ir_manager.py` | Board-free per-tick IR orchestrator: `update()` pumps transmits then receives, owning the pump-before-receive order; exposes `received` + forwarded `last_signal_strength`/`last_error_margin`/`telemetry_line()` |
| `RadioTransport` | `hardware/shared/radio_transport.py` | Board-free half-duplex radio port (`send`/`receive`); the live adapter is `Rfm69RadioTransport` |
| `RadioManager` | `hardware/shared/radio_manager.py` | Board-free per-tick radio receive orchestrator: `update()` polls the transport and exposes `received` (no transmit pump — the chip is half-duplex) |
| `SceneRuntime` | `app/scene_composition.py` | `__slots__` bundle (`manager`, `effect_manager`, `timer`, `ir`, `radio`) returned by `build_scene_runtime`; the wiring `run_scene`'s per-tick loop drives |

---

## Domain vocabulary

Code-facing terms are defined in [`domain-language.md`](domain-language.md) — the single source for the project's vocabulary and the words to avoid. Magic-system vocabulary (elements, auras, spells) lives in the aura-docs vault (`Overview/Magic System.md`).

---

## Coding constraints (CircuitPython and MicroPython compatibility)

All code in `effects/`, `engine/`, `magic/`, and `rules/` must run on CPython, CircuitPython 10.x, and MicroPython. The general CircuitPython/MicroPython rules (no `dataclasses`, `typing.Protocol` unavailable, guarded `typing` imports, no per-frame hot-path allocation) live in the **code-quality skill's embedded-python guidance** (the `embedded-python.md` reference file) — follow it. If that skill isn't installed locally, look it up and copy that file's rules before working on device code. Project-specific deltas on top:

- **`typing.Protocol` substitute** — use plain base classes with `raise NotImplementedError`; subclass explicitly for type-checker compatibility
- **`PaletteLUT256` is pre-computed** — never construct inside a render loop
- **Line limit: 100 characters** — enforced by `ruff` pre-commit hook (also `ruff format`)

`scripts/` is CPython-only and does not carry these constraints.

---

## Tests

~2000 tests spread across `tests/` folders under `effects/`, `engine/`, `magic/`, `hardware/`, `packs/`, and `scripts/`. Run with `python -m pytest`. All must pass before commit. Pre-commit hooks run `python -m ruff` (lint) and `ruff format`.
