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
  render.py       RendererConfig, PixelBuffer, EffectRenderer
  palette.py      Palette, PaletteLUT256 (pre-computed, immutable)
  shape.py        Shape (factory), EffectShapeFunc
  level.py        clamp_level, level_progress, level_lerp, level_lerp_int
  value.py        DynamicValue, Range, ValueGenerator, lerp
  performance.py  PerformanceTracker
  layers/         Layer base class + scroll, flame, drift_noise, sparkle, shape, and renderer compositors
  elements/       One builder function per element + registry.py, ElementBuilder

engine/           Event-driven game loop (CircuitPython/MicroPython-safe)
  engine.py       GameEngine, GameRule, GameState, Version
  events.py       Event, EventGroup
  timer.py        Timer
  effects/
    manager.py    EffectManager, EffectControls, EffectOutput, EffectBuilder, EffectReceipt
    scope.py      Scope, ScopeValue

magic/            Spell and aura game logic (CircuitPython/MicroPython-safe)
  aura.py         Aura, Spell, Spells, SpellTags, SpellLevelScaler, AuraEvent (+ subclasses), EventListener
  caster.py       Caster, CastType (LINE / CONE / AREA_OF_EFFECT)
  values.py       MinMaxValue, ValueWithModifiers, ValueModifier, ValueModifiers, Duration, Counter
  spell/          Individual spell implementations (elemental/, combo/)

rules/            Game-specific rule packs (loaded at runtime, CircuitPython/MicroPython-safe)
scripts/          Deploy and maintenance scripts
```

---

## Key types and relationships

| Type | Lives in | Role |
|------|----------|------|
| `RendererConfig` | `effects/render.py` | Level [1–10], resolution, options, listeners for one render pass |
| `PixelBuffer` | `effects/render.py` | List-backed in-memory pixel buffer of packed RGB values |
| `EffectRenderer` | `effects/render.py` | Base class for all renderers; subclasses implement `name`, `update(elapsed)`, `render(output)` |
| `Layer` | `effects/layers/layer.py` | Base layer: `update(elapsed)` + `sample(position, pixel_count) -> float` |
| `Scroll` | `effects/layers/scroll.py` | Scroll base: `update(elapsed)` + `apply(position) -> float` |
| `LayerRenderer` | `effects/layers/renderer.py` | Single-layer `EffectRenderer` |
| `AddColorsRenderer` | `effects/layers/add_colors_renderer.py` | Composites layers by summing packed RGB colors |
| `AddSamplesRenderer` | `effects/layers/add_samples_renderer.py` | Composites layers by summing float samples then sampling a palette |
| `Palette` / `PaletteLUT256` | `effects/palette.py` | Maps float [0,1] → packed RGB; LUT variant is pre-computed |
| `Shape` | `effects/shape.py` | Factory for `EffectShapeFunc` callables (gradient, sine, checkers, …) |
| `EffectControls` | `engine/effects/manager.py` | Abstract interface: `set_effect`, `add_effect`, `stop_effect` |
| `EffectManager` | `engine/effects/manager.py` | Concrete `EffectControls`; routes effects to outputs by scope |
| `EffectOutput` | `engine/effects/manager.py` | Abstract hardware output: `create_buffer`, `update_pixels`, `handle_event` |
| `EffectBuilder` | `engine/effects/manager.py` | Callable `(name, config) → EffectRenderer`; one per effect pack |
| `EffectReceipt` | `engine/effects/manager.py` | Opaque handle for a running effect instance; used to stop by receipt |
| `ScopeValue` / `Scope` | `engine/effects/scope.py` | Routing keys: `PERSONAL`, `DIRECTIONAL`, `Global.MAIN/BUFF/DEBUFF`, `ALL` |
| `GameEngine` | `engine/engine.py` | Event queue + `GameRule` list; driven by a single `update(timer)` tick |
| `GameState` | `engine/engine.py` | Passed to each rule: holds `engine`, `timer`, `effect_controls` |
| `GameRule` | `engine/engine.py` | Abstract event handler with `name` + `version` |
| `Event` / `EventGroup` | `engine/events.py` | Named events grouped by category |
| `Timer` | `engine/timer.py` | Per-tick elapsed/cumulative time tracker |
| `Aura` | `magic/aura.py` | A player/object's magic pool + active `Spells` collection |
| `Spell` | `magic/aura.py` | Base class for spells; `update` returns `True` to self-remove |
| `Spells` | `magic/aura.py` | Collection with lookup by name, tag, or class |
| `AuraEvent` | `magic/aura.py` | Base event routed through active spells; can be canceled |
| `MinMaxValue` | `magic/values.py` | Clamped float with dynamic max (via `ValueWithModifiers`) |
| `ValueWithModifiers` | `magic/values.py` | Base value + temporary multiplier stack |
| `Duration` | `magic/values.py` | Expiry tracker: `update(elapsed) → bool` |

---

## Domain vocabulary

| Term | Meaning |
|------|---------|
| **Level** | Effect intensity, integer 1–10. 1 = weakest, 10 = strongest. Passed to `RendererConfig.level`. |
| **Resolution** | Drives sample density and buffer size, it is not the pixel count of a strip. |
| **Element** | One of ten named magical elements (Fire, Water, Earth, Ice, Air, Lightning, Light, Dark, Time, Gravity). Each has a buff and a debuff spell. |
| **Effect pack** | An `EffectBuilder` that owns a named set of effects. `ElementBuilder` (from `registry.py`) is one pack; games compose multiple packs at startup. |
| **Scope** | Routing key that maps effects to outputs. `PERSONAL` targets the caster's device; `ALL` targets every registered output. |
| **Receipt** | An `EffectReceipt` returned by `set_effect` / `add_effect`; used to stop a specific running effect instance. |
| **Aura** | A player or object's current magic state: magic pool + active spell list. |
| **Spell power** | Amount of magic at cast time. 1 unit ≈ ambient magic gathered over 1 second in 1 m³. |
| **DynamicValue** | `float | Callable[[], float]` — a value that may be constant or computed each sample. |
| **EffectShapeFunc** | `Callable[[float], float]` — maps a normalized position [0,1] to an output value. |

---

## Coding constraints (CircuitPython and MicroPython compatibility)

All code in `effects/`, `engine/`, `magic/`, and `rules/` must run on CPython, CircuitPython 10.x, and MicroPython. Constraints:

- **No `dataclasses`** — use `__init__` + `__slots__` instead
- **`list[X]` / `dict[K, V]` subscripts are fine** at runtime in CP 10.x
- **`typing.Protocol` is NOT available** — use plain base classes with `raise NotImplementedError`; subclass explicitly for type-checker compatibility
- **Wrap other `typing` imports** in `try/except ImportError` (coverage varies)
- **No per-frame allocation in hot paths** — animation loops must not allocate lists, dicts, or objects on every frame; pre-allocate in `__init__` or use stack-local vars
- **`PaletteLUT256` is pre-computed** — never construct inside a render loop
- **Line limit: 100 characters** — enforced by `ruff` pre-commit hook (also `ruff format`)

`scripts/` is CPython-only and does not carry these constraints.

---

## Tests

760 tests under `effects/tests/`, `engine/tests/`, `magic/tests/`, `rules/`, and `scripts/tests/`. Run with `python -m pytest`. All must pass before commit. Pre-commit hooks run `python -m ruff` (lint) and `ruff format`.
