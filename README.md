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
packs/       First-party effect, rule, and scene packs (elements, red_light_green_light, hardware_test, …)
hardware/    Hardware drivers and shared abstractions for CircuitPython props
magic/       Spell and aura game logic (elements, buffs/debuffs, cast types)
scripts/     Deploy and maintenance scripts (CPython-only)
```

See [`docs/domain.md`](docs/domain.md) for key types and constraints, and [`docs/domain-language.md`](docs/domain-language.md) for the domain glossary.

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
   EffectOutput           hardware: RGB strip, audio, haptic
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

---

## Hardware configuration (`aura-device.json`)

Every hardware example (`examples/hardware/`) boots from an `aura-device.json` file at the
CIRCUITPY drive root, loaded by `hardware.circuitpython.device_builder.load_device_config()`.
If the file is absent the built-in default (PropMaker + IS31FL3741 matrix) is used.

### Schema

```json
{
  "pixels": {
    "type": "matrix",
    "cols": 13,
    "scope_rows": {
      "global.buff": [0, 1], "global.debuff": [1, 2], "global.main": [2, 5],
      "personal": [5, 7], "directional": [7, 8], "ambient": [8, 9]
    }
  },
  "buttons": ["D9", "D10"],
  "ir": {
    "rx": "D11",
    "line": "D12",
    "cone": "D13",
    "area_of_effect": "D14"
  },
  "audio": {
    "voices": 2,
    "max_volume": 0.1
  }
}
```

**`pixels`** — required. `type` is `"matrix"` (IS31FL3741) or `"neopixel"`.

- `"matrix"`: `cols` (int) + `scope_rows` (scope key → `[start_row, end_row]`)
- `"neopixel"`: `scopes` map — each entry: `pin` (board pin name), `count` (int),
  optional `order` (default `"GRB"`), optional `brightness` (0.0–1.0, default 1.0)

**`buttons`** — required. List of board pin name strings.

**`ir`** — optional. `rx` (receiver pin) + at least `line` emitter. Optional `cone` and
`area_of_effect` emitters. The wire-frame codec is selected per scene: `build_hardware()` wires
the IR subsystem with its default Aura codec, then `run_scene` reads the active scene's declared
`ir_codec` (`scene.json`, default `"aura"`) via `resolve_ir_codec` and applies the resolved
encoder/decoder onto the built hardware via `hw.ir.apply_codec()` before the first tick — the
`tag` scene declares `"ir_codec": "tag"`.

**`audio`** — optional. `voices` (int, ≥ 1), `max_volume` (0.0–1.0). Clip resolution is
`AudioRegistry`'s job (base scanned from `packs/effects/*/sounds`, overlay installed per
scene), not a device-config concern.

### Running an example

Every scene (e.g. `hardware_test`, `red_light_green_light`, `element_browser`, `tag`) is
selected via the `default_scene` key in `aura-settings.json` and run through the single
`scene_demo.py` entry point — including `tag`, whose `scene.json` declares the Tag IR
wire-frame codec so it is wired in automatically. `run_scene` resolves the boot scene
only after hardware is brought up (so any SD card is mounted): a `scene` value persisted
to the SD card's `aura-state.json` overrides `default_scene`; a card-less device, or one
with nothing persisted, boots the flash default unaffected. Neither a persisted
selection nor a flash default set raises, naming both `aura-state.json` and
`aura-settings.json`.

`aura-settings.json`:

```json
{
  "default_scene": "tag"
}
```

`aura-device.json`:

```json
{
  "pixels": { "..." : "..." },
  "buttons": ["D9", "D10"]
}
```

```sh
# Deploy scene_demo with a scene selected in aura-settings.json:
python scripts/deploy_watch.py examples/hardware/scene_demo.py
```

---

## Licensing

This repo splits licensing by area:

- **Software** (`effects/`, `engine/`, `magic/`, `packs/`, `hardware/`, `app/`, `scripts/`, …) —
  [MIT](LICENSE).
- **Hardware designs** (`electronics/`) — CERN-OHL-P-2.0, governed by
  `electronics/LICENSE`.
- **Documentation** (`docs/`) — [CC-BY-4.0](docs/LICENSE).

Each area's `LICENSE` file is authoritative for its scope; `pyproject.toml` declares the
software license for tooling. No per-file license headers are used.

