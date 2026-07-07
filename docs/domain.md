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
  effect.py       EffectConfig, PixelBuffer, Effect, EffectPixels, EffectAudio, EffectVibration,
                  AudioPlaybackConfig, VibrationConfig
  palette.py      Palette, PaletteLUT256 (pre-computed, immutable)
  shape.py        Shape (factory), EffectShapeFunc
  level.py        clamp_level, level_progress, level_lerp, level_lerp_int
  value.py        DynamicValue, ValueGenerator, lerp
  performance.py  PerformanceTracker
  layers/         Layer base class + scroll, flame, drift_noise, sparkle, shape, progress, pulse
                  layers and the renderer compositors

engine/           Event-driven game loop (CircuitPython/MicroPython-safe)
  engine.py       GameEngine, GameRule
  state.py        GameState, EffectControls, EffectReceipt, NetworkControls, Scope, ScopeValue
  scene.py        Scene, SceneRegistry, SceneLocalRegistry, SceneManager, SceneControls
  phase.py        PhaseKey, PhaseMachine, PhaseRule, InPhaseRule
  events.py       Event, EventGroup, EffectEvent
  timer.py        Timer
  lerp.py         Integer/float interpolation helpers
  packs.py        PackRegistry
  version.py      Pack semver parsing and comparison
  input.py        ButtonData, AccelerationData, InputEvents
  audio.py        AudioRegistry
  network.py      NetworkEvents, HardwareNetworkControls, TransmitPump
  effects/
    manager.py    EffectManager, EffectBuilder, EffectResolver
    output.py     EffectOutput (abstract hardware output port)
    merge.py      MergeStrategy, SplitMerge, AdditiveMerge (per-scope layered-buffer compositing)

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
                  neopixel_output, audio_output, infrared_io, counting_i2c)
  shared/         Hardware-agnostic helpers (matrix_output, voice_pool, debounced_buttons,
                  device_config, device_hardware, scene_selection, scene_runtime, ir_transport,
                  ir_protocol, tag_protocol, ir_telemetry, profiling_helpers)

scripts/          Deploy and maintenance scripts (CPython-only)
```

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
| `EffectControls` | `engine/state.py` | Abstract interface: `set_effect`, `add_effect`, `stop_effect` |
| `EffectManager` | `engine/effects/manager.py` | Concrete `EffectControls`; routes effects to outputs by scope |
| `EffectOutput` | `engine/effects/output.py` | Abstract hardware output: `create_buffer`, `update_pixels`, `handle_event` |
| `EffectBuilder` | `engine/effects/manager.py` | Callable `(name, config) → Effect`; one per effect pack |
| `EffectReceipt` | `engine/state.py` | Opaque handle for a running effect instance; used to stop by receipt |
| `ScopeValue` / `Scope` | `engine/state.py` | Routing keys: `PERSONAL`, `DIRECTIONAL`, `Global.MAIN/BUFF/DEBUFF`, `ALL` |
| `NetworkControls` | `engine/state.py` | Abstract interface for sending/receiving network messages |
| `TransmitPump` | `engine/network.py` | Abstract runtime-facing seam declaring `poll_transmits()`; the type the runtime loop reaches through, distinct from the send-only `NetworkControls` |
| `GameEngine` | `engine/engine.py` | Event queue + `GameRule` list; driven by a single `update(timer)` tick |
| `GameState` | `engine/state.py` | Passed to each rule: holds `engine`, `timer`, `effect_controls`, `network_controls` |
| `GameRule` | `engine/engine.py` | Abstract event handler with `name` + `version` |
| `Scene` | `engine/scene.py` | Named game mode with its own effect and rule registries |
| `SceneManager` | `engine/scene.py` | Activates/deactivates scenes; owns `SceneLocalRegistry` per scene |
| `PhaseKey` / `PhaseMachine` | `engine/phase.py` | Identity-typed phase constant; per-scene current-phase holder |
| `PhaseRule` / `InPhaseRule` | `engine/phase.py` | Phase-owning rule (lifecycle + transitions) vs. phase-gated reactor |
| `EffectResolver` | `engine/effects/manager.py` | Resolves a qualified effect name to a builder; owns the `scene.` prefix rule |
| `MergeStrategy` | `engine/effects/merge.py` | Per-scope policy compositing a scope's layered effect buffers into one region buffer (`SplitMerge` / `AdditiveMerge`) |
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
| `DeviceConfig` | `hardware/shared/device_config.py` | Validated `aura-device.json`; `pixels` is a list of `MatrixPixelsConfig` / `NeoPixelPixelsConfig` |
| `DeviceHardware` | `hardware/shared/device_hardware.py` | Named bundle `build_hardware` returns (outputs, buttons, network_controls, transmit_pump, …); board-free, importable under CPython |

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
