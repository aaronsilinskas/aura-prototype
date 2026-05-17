# Domain: aura-prototype

## What this project is

`aura-prototype` is the Python/CircuitPython animation and game-logic engine for the **Aura** live-action game platform. Aura is a physical magic game played with custom props (wands, targets, tokens) powered by micropython-compatible microcontrollers.

This repo implements:
- A composable LED animation engine (the `effects/` package) that runs on both CPython and CircuitPython
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
  effect.py       Effect, EffectState, EffectStep, SharedStateKey, EffectTimer
  render.py       RendererConfig, PixelBuffer, EffectRenderer, merge renderers
  palette.py      Palette, PaletteLUT256 (pre-computed, immutable)
  shape.py        Shape — maps sample positions to pixel indices
  level.py        level_lerp / level_lerp_int — intensity scaling helpers
  value.py        Dynamic value types (constants, noise, ranges, etc.)
  steps/          EffectStep implementations (flame, sparkle, drift_noise, …)
  elements/       One builder function per element + registry.py
  manager/        EffectManager, EffectOutput, EffectBuilder, Scope, ScopeValue

magic/            Spell and aura game logic
  aura.py         Aura, Spell, SpellLevelScaler
  caster.py       Caster, CastType (line / cone / aoe)
  values.py       MinMaxValue, ValueWithModifiers
  spell/          Individual spell implementations (elemental/, combo/)

engine/           Event-driven game loop
  engine.py       GameEngine, GameRule, GameState
  events.py       Event
  timer.py        Timer, EffectTimer

rules/            Game-specific rule packs (loaded at runtime)
scratch/          Throwaway experiments — ignore
```

---

## Key types and relationships

| Type | Lives in | Role |
|------|----------|------|
| `Effect` | `effects/effect.py` | Immutable chain of `EffectStep` instances; stateless |
| `EffectState` | `effects/effect.py` | All mutable per-animation state; one per running effect |
| `EffectTimer` | `effects/effect.py` | Elapsed time; passed into each step update |
| `RendererConfig` | `effects/render.py` | Level [1–10], resolution, options, listeners for one render pass |
| `PixelBuffer` | `effects/render.py` | In-memory list of packed RGB values; maps 1:1 with LED strip |
| `EffectRenderer` | `effects/render.py` | Pairs an `Effect` + `Palette`; samples the effect into a `PixelBuffer` |
| `Palette` / `PaletteLUT256` | `effects/palette.py` | Maps float [0,1] → RGB; LUT variant is pre-computed and fast |
| `EffectManager` | `effects/manager/manager.py` | Lifecycle manager; routes effects to `EffectOutput` instances by scope |
| `EffectOutput` | `effects/manager/manager.py` | Interface: `update_pixels(buffer)` + `handle_event(name)` |
| `EffectBuilder` | `effects/manager/manager.py` | Callable `(name, config) → EffectRenderer`; one per "effect pack" |
| `ScopeValue` / `Scope` | `effects/manager/scope.py` | Routing keys: `PERSONAL`, `DIRECTIONAL`, `Global.MAIN/BUFF/DEBUFF`, `ALL` |
| `Aura` | `magic/aura.py` | A player/object's magic pool + list of active `Spell` instances |
| `GameEngine` | `engine/engine.py` | Event queue + list of `GameRule` instances; driven by a single `update(timer)` tick |

---

## Domain vocabulary

| Term | Meaning |
|------|---------|
| **Level** | Effect intensity, integer 1–10. 1 = weakest, 10 = strongest. Passed to `RendererConfig.level`. |
| **Resolution** | Pixel count of the target LED strip. Drives sample density and buffer size. |
| **Element** | One of ten named magical elements (Fire, Water, Earth, Ice, Air, Lightning, Light, Dark, Time, Gravity). Each has a buff and a debuff spell. |
| **Effect pack** | An `EffectBuilder` that owns a named set of effects. `ElementRegistryBuilder` is one pack; games compose multiple packs at startup. |
| **Scope** | Routing key that maps effects to outputs. `PERSONAL` targets the caster; `ALL` targets every registered output. |
| **Aura** | A player or object's current magic state: magic pool + list of active spells. |
| **Spell power** | Amount of magic at cast time. 1 unit ≈ ambient magic gathered over 1 second in 1 m³. |

---

## Coding constraints (CircuitPython compatibility)

All code in `effects/` must run on both CPython and CircuitPython. CircuitPython limitations:

- **No `dataclasses`** — use `__init__` + `__slots__` instead
- **No generics** — no `T = TypeVar(...)` or `list[T]` at runtime
- **Wrap all `typing` imports** in `try/except ImportError`
- **No per-frame allocation in hot paths** — animation loops must not allocate lists, dicts, or objects on every frame; pre-allocate in `__init__` or use stack-local vars that the GC can reclaim cheaply
- **`PaletteLUT256` is pre-computed** — never call `PaletteLUT256(palette)` inside a render loop
- **Line limit: 100 characters** — enforced by `ruff` in the pre-commit hook

`magic/` and `engine/` are CPython-only and do not carry the CircuitPython constraint.

---

## Tests

469 tests under `effects/tests/`, `engine/tests/`, and `magic/tests/`. Run with `pytest`. All must pass before commit. Pre-commit hooks run `ruff` (lint) and `ruff format`.
