# Aura Prototype

The prototype firmware and game engine for **Aura**, a platform for interactive
adventure games played in the real world with handheld devices and props that light
up, make sound, and react to how you play. Aura is being built by
[Mindwidgets](https://mindwidgets.com); the site explains what Aura is and
[how it works today](https://mindwidgets.com/aura/how-it-works/).

This repository is where the software is worked out: a game engine that turns
buttons, motion, infrared, and radio into games, and an animation engine for the
lights, sound, and vibration players get back. It is written in Python and runs on
[CircuitPython](https://circuitpython.org/) microcontrollers, and most of it also
runs on a desktop so it can be tested without hardware.

---

## Status

Aura is in prototype. This is working code under active development, not a kit.

- **You can't buy or build an Aura device yet.** There are no build instructions,
  parts list, or finished circuit board designs here. `electronics/` holds only
  rough sketches so far. The prototype is hand-wired from off-the-shelf breakout
  boards.
- **You can read the code, run the tests, and watch the effects in a terminal**
  without any hardware. See [Try it without hardware](#try-it-without-hardware).
- **The games are in `packs/scenes/`**, one folder per scene, alongside scenes for
  testing hardware and browsing effects.

Issues and pull requests are not being sought yet. To hear when there is something
to build or play, sign up at [mindwidgets.com](https://mindwidgets.com).

---

## What is in here

```
effects/      Composable animation engine for lights, sound, and vibration
engine/       Event-driven game loop: rules, scenes, state, packs, and I/O abstractions
packs/        Shared effects and rules, and the scenes (games) built from them
magic/        Spell and aura game logic (elements, buffs and debuffs, cast types)
hardware/     CircuitPython drivers and the hardware abstractions above them
app/          Wires the engine to the hardware and runs a scene on a device
examples/     Entry points: a desktop terminal demo and the on-device scene runner
scripts/      Deploy and maintenance scripts that run on the desktop
electronics/  Circuit board designs (rough sketches only, so far)
docs/         Domain map, glossary, and hardware measurements
```

A few words used throughout the code:

- A **rule** is how a game responds to player input, communications, and time.
- An **effect** is what players see, hear, and feel.
- A **scene** is a game: the rules and effects that combine into it.
- A **pack** is a set of rules or effects that more than one scene can use. The
  elemental magic effects (fire, water, lightning, and the rest) are a pack.

See [`docs/domain.md`](docs/domain.md) for key types and constraints, and
[`docs/domain-language.md`](docs/domain-language.md) for the full glossary.

---

## Try it without hardware

You need Python 3.10 or newer and [uv](https://docs.astral.sh/uv/).

```sh
uv sync            # install the development tools
uv run pytest      # run the test suite
```

To watch the effects engine run, start the terminal demo from the repository root
(macOS or Linux, in a terminal with 24-bit color):

```sh
PYTHONPATH=. uv run python examples/ansi-multi-effect-demo.py
```

Press `a` for fire, `b` for water, `c` for lightning, `d` to stop them all, and `q`
to quit.

---

## Hardware the prototype uses

There is no single finished device. The firmware builds whichever of these parts the
device's config file declares, and leaves out the rest:

| Part | What the code supports |
|------|------------------------|
| Microcontroller | RP2350 with PSRAM, running CircuitPython 10 |
| Lights | IS31FL3741 13×9 RGB LED matrix, NeoPixel strips |
| Sound | I2S audio output |
| Vibration | DRV2605L haptic driver |
| Motion | LIS3DH accelerometer, MMC5603 magnetometer |
| Buttons | Any GPIO pins |
| Infrared | Up to three emitters (line, cone, and area) and one or more receivers |
| Radio | RFM69HCW at 915 MHz |
| Storage | SD card over SPI |

Measurements taken on real hardware are in
[`docs/hardware/recorded-metrics.md`](docs/hardware/recorded-metrics.md). The
infrared and radio links were tested with two separate tools,
[infrared-analyzer](https://github.com/aaronsilinskas/infrared-analyzer) and
[rfm69-analyzer](https://github.com/aaronsilinskas/rfm69-analyzer).

---

## Running on a device

These are working notes for a hand-wired prototype, not a build guide.

A device reads two JSON files from the root of its `CIRCUITPY` drive. Both are
required; there are no built-in defaults.

- **`aura-device.json`** declares the hardware: which parts are fitted and which
  pins they use. Each part is built only if its section is present and enabled.
  [`examples/aura-device.rasppi-pico-2.json`](examples/aura-device.rasppi-pico-2.json)
  is a complete example for a Raspberry Pi Pico 2.
- **`aura-settings.json`** picks the scene to boot, by its folder name under
  `packs/scenes/`:

  ```json
  {
    "default_scene": "red_light_green_light"
  }
  ```

  If the device has an SD card, a scene saved to the card's `aura-state.json`
  takes priority over `default_scene`.

To put the code on a board:

1. Install CircuitPython 10 on the board, and copy the Adafruit libraries for the
   parts you declared into `CIRCUITPY/lib/`.
2. Download the matching `mpy-cross` compiler: `scripts/setup_mpy_cross.sh`
3. Copy both JSON files to the `CIRCUITPY` drive.
4. Deploy the scene runner and all modules:

   ```sh
   uv run python scripts/deploy.py examples/hardware/scene_demo.py
   ```

   The board reboots and starts the scene.

### `aura-device.json` in brief

```json
{
  "pixels": [
    {
      "type": "matrix",
      "cols": 13,
      "scope_rows": {
        "global.buff": [0, 1], "global.debuff": [1, 2], "global.main": [2, 5],
        "personal": [5, 7], "directional": [7, 8], "ambient": [8, 9]
      }
    }
  ],
  "buttons": ["GP26", "GP27"],
  "ir": {
    "rx": "GP13",
    "line": "GP10",
    "cone": "GP11",
    "area_of_effect": "GP12"
  },
  "audio": {
    "voices": 2,
    "max_volume": 0.1,
    "i2s_bit_clock": "GP7",
    "i2s_word_select": "GP8",
    "i2s_data": "GP6"
  }
}
```

- **`pixels`** is a list of light outputs. `type` is `"matrix"` (IS31FL3741, at most
  one) or `"neopixel"`. Each entry maps **scopes**, the named regions an effect can
  be shown in, to rows of the matrix (`scope_rows`) or to pixel ranges of a strip
  (`scope_pixels`).
- **`buttons`** is a list of board pin names.
- **`ir`** takes `rx` (one receiver pin, or a list of them) and at least a `line`
  emitter; `cone` and `area_of_effect` emitters are optional. Each scene chooses
  the infrared message format it uses: Aura's own by default, or the `tag` scene's
  format, which works with off-the-shelf infrared tag gear.
- **`audio`** takes `voices` (how many sounds can play at once), `max_volume`
  (0.0 to 1.0), and the three I2S pins.

The example file also shows the `accelerometer`, `magnetometer`, `haptics`, `radio`,
`sdcard`, `i2c`, `spi`, and `high_current_rail` sections.

---

## How the engine works

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

- **Effect pack** — each `.py` file exports `BUILD`: a `(config) → Effect` callable.
  Effect names use `"pack.effect"` format (e.g. `"elements.fire"`).
- **Rule pack** — each `.py` file exports `RULE`: a `GameRule` instance.

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

## Licensing

This repo splits licensing by area:

- **Software** (`effects/`, `engine/`, `magic/`, `packs/`, `hardware/`, `app/`, `scripts/`, …) —
  [MIT](LICENSE).
- **Hardware designs** (`electronics/`) — CERN-OHL-P-2.0, governed by
  `electronics/LICENSE`.
- **Documentation** (`docs/`) — [CC-BY-4.0](docs/LICENSE).

Each area's `LICENSE` file is authoritative for its scope; `pyproject.toml` declares the
software license for tooling. No per-file license headers are used.
