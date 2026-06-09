# Aura Prototype

Monorepo for the Aura game engine — a composable LED animation and event-driven
game logic engine that runs on CPython and CircuitPython/MicroPython.

The engine powers physical magic game props (wands, targets, tokens) running on
microcontrollers. Full game and hardware design lives in `~/dev/aura/aura-docs/`.

---

## Module Layout

```
effects/     Composable LED animation engine; runs on CPython and CircuitPython
engine/      Event-driven game loop: rules, scenes, state, packs, and I/O abstractions
packs/       First-party effect, rule, and scene packs (elements, rlgl, hw_test, …)
hardware/    Hardware drivers and shared abstractions for CircuitPython props
magic/       Spell and aura game logic (elements, buffs/debuffs, cast types)
scripts/     Deploy and maintenance scripts (CPython-only)
```

See [`docs/agents/domain.md`](docs/agents/domain.md) for key types, vocabulary, and constraints.

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

- **Effect pack** — each `.py` file exports `builder`: a `(config) → Effect` callable.
  Effect names use `"pack.effect"` format (e.g. `"elements.fire"`).
- **Rule pack** — each `.py` file exports `rule`: a `GameRule` instance.

Version format is `MAJOR.MINOR`. A `Scene` declares minimum required versions;
`SceneManager` validates at load time (same-major, installed-minor ≥ required-minor).

### Scenes

A **Scene** is a declarative bundle:

- `effect_packs: list[tuple[str, str]]` — `(pack_name, min_version)` pairs; version-validated at load
- `rule_packs: list[tuple[str, str]]` — `(pack_name, min_version)` pairs; all rules loaded and appended
- Optional `initial_data: dict` — seed values for `GameState.data`

`SceneManager` owns a scene stack. `load(name)` replaces the stack; `overlay(name)` pushes
on top (suspending the current scene); `pop()` restores the previous scene. Transitions are
deferred to end-of-tick — rules call `state.scene_controls.load/overlay/pop()` during a tick
and the transition is applied after `engine.update(state)` returns. Every scene the manager
unloads or suspends has its effects stopped on `Scope.ALL` automatically.

