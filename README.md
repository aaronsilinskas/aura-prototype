# Aura Prototype

Monorepo for the Aura game engine — a composable LED animation and event-driven
game logic engine that runs on CPython and CircuitPython/MicroPython.

The engine powers physical magic game props (wands, targets, tokens) running on
microcontrollers. Full game and hardware design lives in `~/dev/aura/aura-docs/`.

---

## Module Layout

```
effects/          LED animation engine (CircuitPython-safe)
  render.py       RendererConfig, PixelBuffer, EffectRenderer, EffectTimer
  palette.py      Palette, PaletteLUT256
  shape.py        Shape (factory), EffectShapeFunc
  level.py        clamp_level, level_progress, level_lerp, level_lerp_int
  value.py        DynamicValue, Range, ValueGenerator, lerp
  performance.py  PerformanceTracker
  layers/         Layer, Scroll, ScrollLayer, FlameLayer, DriftNoiseLayer, SparkleLayer, ShapeLayer, renderers

engine/           Event-driven game loop (CircuitPython/MicroPython-safe)
  engine.py       GameEngine, GameRule, GameState
  events.py       Event, EventGroup
  timer.py        Timer
  packs.py        PackRegistry — multi-pack discovery and lazy loading  [#86]
  scene.py        Scene, SceneControls, SceneManager  [#85]
  effects/
    manager.py    EffectManager, EffectControls, EffectOutput, EffectReceipt
    scope.py      Scope, ScopeValue

packs/            First-party game content packs  [#86]
  effects/
    elements/     Element effect builders (Fire, Water, Earth, …)  ← from effects/elements/
  rules/
    debug/        Debug rule pack (button events, event logger)  ← from rules/debug/

magic/            Spell and aura game logic (CircuitPython/MicroPython-safe)
  aura.py         Aura, Spell, Spells, SpellTags, AuraEvent, EventListener
  caster.py       Caster, CastType
  values.py       MinMaxValue, ValueWithModifiers, ValueModifier, Duration, Counter
  spell/          Individual spell implementations (elemental/, combo/)

scripts/          Deploy and maintenance scripts
```

Items marked `[#86]` or `[#85]` are planned but not yet implemented.

---

## Architecture

### Event flow

```
(InputEvent | NetworkEvent)
        │
        ▼
   GameEngine             holds rule list; stateless — caller owns GameState
        │  engine.update(state)
        ▼
   GameRule.handle_event(event, state)
        │  rules read/write state.data, queue new events,
        │  call state.effect_controls, call state.scene_controls
        ▼
   EffectManager          routes effects to EffectOutput by scope
        │
        ▼
   EffectOutput           hardware: RGB strip, audio, vibration
```

Rules are stateless — all mutable game data lives in `GameState.data`. Rules
read and write `state.data`, fire effects via `state.effect_controls`, and
trigger scene transitions via `state.scene_controls`.

### Packs

A **pack** is a directory containing a `version.txt` and one `.py` file per
item. `PackRegistry` discovers packs via `scan_dir(path, module_prefix)` and
imports items lazily on first use.

- **Effect pack** — each `.py` file exports `builder`: a `(config) → EffectRenderer` callable.
  Effect names use `"pack.effect"` format (e.g. `"elements.fire"`).
- **Rule pack** — each `.py` file exports `rule`: a `GameRule` instance.

Version format is `MAJOR.MINOR`. A `Scene` declares minimum required versions;
`SceneManager` validates at load time (same-major, installed-minor ≥ required-minor).

### Scenes

A **Scene** is a declarative bundle:

- `rules: list[GameRule]` — direct rule instances
- `effect_packs: list[tuple[str, str]]` — `(pack_name, min_version)` pairs; version-validated at load
- `rule_packs: list[tuple[str, str]]` — `(pack_name, min_version)` pairs; all rules loaded and appended
- Optional `initial_data: dict` — seed values for `GameState.data`
- Optional lifecycle callbacks: `on_load(ec)`, `on_unload(ec)`, `on_suspend(ec)`, `on_resume(ec)`

`SceneManager` owns a scene stack. `load(name)` replaces the stack; `overlay(name)` pushes
on top (suspending the current scene); `pop()` restores the previous scene. Transitions are
deferred to end-of-tick — rules call `state.scene_controls.load/overlay/pop()` during a tick
and the transition is applied after `engine.update(state)` returns.

---

## Key Types

| Type | Module | Role |
|------|--------|------|
| `GameEngine` | `engine/engine.py` | Rule list; driven by `update(state)`; `create_state()` factory |
| `GameRule` | `engine/engine.py` | Abstract stateless event handler |
| `GameState` | `engine/engine.py` | Per-tick context passed to every rule: `data`, `effect_controls`, `scene_controls`, `timer` |
| `PackRegistry` | `engine/packs.py` | Multi-pack discovery, version checks, lazy item import |
| `Scene` | `engine/scene.py` | Declarative game context bundle |
| `SceneManager` | `engine/scene.py` | Scene stack; `load`, `overlay`, `pop`; owns two `PackRegistry` instances |
| `SceneControls` | `engine/scene.py` | Abstract interface for scene transitions from within rules |
| `EffectControls` | `engine/effects/manager.py` | Abstract interface: `set_effect`, `add_effect`, `stop_effect` |
| `EffectManager` | `engine/effects/manager.py` | Concrete `EffectControls`; routes `"pack.effect"` names to outputs by scope |
| `EffectOutput` | `engine/effects/manager.py` | Abstract hardware output: `create_buffer`, `update_pixels`, `handle_event` |
| `EffectReceipt` | `engine/effects/manager.py` | Opaque handle for a running effect; used to stop by receipt |
| `Scope` / `ScopeValue` | `engine/effects/scope.py` | Routing keys: `PERSONAL`, `DIRECTIONAL`, `Global.*`, `ALL` |
| `RendererConfig` | `effects/render.py` | Level [1–10], resolution, options for one render pass |
| `EffectTimer` | `effects/render.py` | Duration + elapsed tracking; passed to each renderer's `update` |
| `PixelBuffer` | `effects/render.py` | In-memory packed-RGB pixel buffer |
| `EffectRenderer` | `effects/render.py` | Base class; subclasses implement `name`, `update(timer)`, `render(output)` |
| `Layer` | `effects/layers/layer.py` | Simulation layer: `update(elapsed)` + `sample(position, pixel_count) -> float` |
| `Palette` / `PaletteLUT256` | `effects/palette.py` | Maps float [0,1] → packed RGB |
| `Aura` | `magic/aura.py` | Player magic pool + active spell list |
| `Spell` | `magic/aura.py` | Base spell; `update` returns `True` to self-remove |

---

## Domain Vocabulary

| Term | Meaning |
|------|---------|
| **Level** | Effect intensity, integer 1–10. Passed to `RendererConfig.level`. |
| **Resolution** | Sample density and buffer size — not the physical pixel count. |
| **Element** | One of ten magic elements: Fire, Water, Earth, Ice, Air, Lightning, Light, Dark, Time, Gravity. |
| **Effect pack** | A directory of `EffectBuilder` modules discovered by `PackRegistry`. Named `"pack.effect"` at call sites. |
| **Rule pack** | A directory of `GameRule` modules discovered by `PackRegistry`. Each file exports `rule = <GameRule instance>`. |
| **Scope** | Routing key that maps effects to outputs. `PERSONAL` targets the caster; `ALL` targets every output. |
| **Receipt** | An `EffectReceipt` returned by `set_effect`/`add_effect`; used to stop a specific running effect. |
| **Scene** | Declarative bundle of rules + pack references + optional lifecycle callbacks. |
| **Aura** | A player or object's current magic state: magic pool + active spells. |

---

## Constraints

- **`__slots__` required** on all engine and effects types — no `__dict__` on CircuitPython.
- **No `dataclasses` or `typing.Protocol`** — not available on CircuitPython.
- **100-character line limit** enforced by `ruff`.
- **No heap allocation in hot paths** — avoid list/dict creation inside `update()` loops.
- Pack item import uses `__import__` directly (no `importlib`) for CircuitPython compatibility.