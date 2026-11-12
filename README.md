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
docs/         Domain map and architecture decision records (the glossary is GLOSSARY.md)
```

A few words used throughout the code:

- A **rule** is how a game responds to player input, communications, and time.
- An **effect** is what players see, hear, and feel.
- A **scene** is a game: the rules and effects that combine into it.
- A **pack** is a set of rules or effects that more than one scene can use. The
  elemental magic effects (fire, water, lightning, and the rest) are a pack.

See [`docs/domain.md`](docs/domain.md) for key types and constraints, and
[`GLOSSARY.md`](GLOSSARY.md) for the full glossary.

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
| Microcontroller | RP2350 with PSRAM, running CircuitPython 10. Pimoroni's Pico 2 boards with PSRAM work well, for example the [Pico Plus 2](https://shop.pimoroni.com/products/pimoroni-pico-plus-2) or [Pico LiPo 2](https://shop.pimoroni.com/products/pimoroni-pico-lipo-2). A standard Raspberry Pi Pico 2 has no PSRAM and will not work |
| Lights | IS31FL3741 13×9 RGB LED matrix, NeoPixel strips |
| Sound | I2S audio output |
| Vibration | DRV2605L haptic driver |
| Motion | LIS3DH accelerometer, MMC5603 magnetometer |
| Buttons | Any GPIO pins |
| Infrared | Up to three emitters (line, cone, and area) and one or more receivers |
| Radio | RFM69HCW at 915 MHz |
| Storage | SD card over SPI |

The infrared and radio links were tested with two separate tools,
[infrared-analyzer](https://github.com/aaronsilinskas/infrared-analyzer) and
[rfm69-analyzer](https://github.com/aaronsilinskas/rfm69-analyzer).

---

## Running on a device

These are working notes for a hand-wired prototype, not a build guide.

A device reads two JSON files from the root of its `CIRCUITPY` drive. Both are
required; there are no built-in defaults.

- **`aura-device.json`** declares the hardware: which parts are fitted and which
  pins they use. Each part is built only if its section is present and enabled.
  [`examples/aura-device.pico-2.json`](examples/aura-device.pico-2.json)
  is a complete example, tested on Pimoroni Pico 2 boards.
  [`examples/aura-device.simulated.json`](examples/aura-device.simulated.json)
  is for the test-only Simulated device, not for flashing to a board.
- **`aura-boot.json`** picks the scene to boot, by its folder name under
  `packs/scenes/`, as in
  [`examples/aura-boot.json`](examples/aura-boot.json):
  `{"default_scene": "hardware_test"}`.

  If the device has an SD card, a scene saved to the card's `aura-state.json`
  takes priority over `default_scene`.

To put the code on a board:

1. Install CircuitPython 10 on the board, and copy the Adafruit libraries for the
   parts you declared into `CIRCUITPY/lib/`.
2. Download the matching `mpy-cross` compiler: `scripts/setup_mpy_cross.sh`
3. Copy both JSON files to the `CIRCUITPY` drive.
4. Deploy the scene runner and all modules:

   ```sh
   uv run python -m scripts.deploy examples/hardware/scene_demo.py
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
`sdcard`, `i2c`, `spi`, and `neopixel_current_budget` sections.
`neopixel_current_budget` is optional: when the NeoPixel strips could draw more than
`current_limit_ma` at full white, the device dims them at boot to fit, never below
`min_brightness`.

---

## How the engine works

### Event flow

```
(InputEvent | NetworkEvent)
        │
        ▼
   SceneRun               one per running scene: its GameState + rules in dispatch order
        │  run.tick(elapsed)
        ▼
   GameRule.handle_event(event, state)
        │  rules read/write state.get/state.set, queue new events,
        │  call state.effect_controls, call state.scene_controls
        ▼
   EffectManager          routes effects to EffectOutput by scope
        │
        ▼
   EffectOutput           hardware: lights, audio, haptics
```

Rules are stateless: all mutable game data lives in the scene's `GameState`.
Rules fire effects through `state.effect_controls`, read Settings through
`state.settings`, and leave or cover the scene through `state.scene_controls`.

### Packs and scenes

Each folder under `packs/` with a manifest is a pack, and each folder under
`packs/scenes/` is a scene. One scan at boot finds them all and checks every
declaration, so a bad pack or scene fails before anything runs. Pack items are
imported only when first used.

- **Effect pack**: manifest `effects.json`; each `.py` file exports `BUILD`, a
  `(config) → Effect` callable. Effects are named `"pack.effect"`, e.g.
  `"elements.fire"`.
- **Rule pack**: manifest `rules.json`; each `.py` file exports `RULE`, a
  `GameRule` instance. Its manifest can also declare **Settings** and the
  **Capabilities** the rules need:

```json
{
  "version": "1.0",
  "requires": ["button.A", "button.B"],
  "settings": {
    "hold_seconds": {"type": "float", "default": 5.0, "description": "Seconds to hold."}
  }
}
```

A scene is described by its `scene.json`:

```json
{
  "version": "1.0",
  "effect_packs": [{"name": "elements", "version": "1.0"}],
  "rule_packs": [
    {"name": "return_to_lobby", "version": "2.0", "settings": {"hold_seconds": 2.0}}
  ],
  "settings": {
    "window_seconds": {"type": "float", "default": 3.0, "description": "Seconds per window."}
  },
  "requires": ["accelerometer"],
  "ir_codec": "aura"
}
```

| Key | Meaning |
|-----|---------|
| `version` | The scene's own `MAJOR.MINOR` version |
| `effect_packs`, `rule_packs` | Packs in load order. Each `version` is the minimum compatible one: same major, installed minor at least this. A rule pack reference may override that pack's Settings |
| `settings` | Optional. The scene's own Settings, in the manifest's shape |
| `requires` | Optional. Capabilities the scene can't be played without, on top of its rule packs' |
| `ir_codec` | Optional. The infrared message format: `"aura"` (default) or `"tag"` |

A Setting's `type` is `int`, `float`, `bool`, `str` or `list`. One with no
`default` must be set by every scene that uses the pack. Rules read Settings with
`state.settings.get_float("scene", "window_seconds")` and its siblings, by
namespace (`"scene"` or the pack's name).

A **Capability** is hardware a scene can depend on: `button.A` … `button.Z`
(labelled in the order `buttons` lists them), `ir.line`, `ir.cone`,
`ir.area_of_effect`, `ir.receive`, `radio`, `storage`, `accelerometer`,
`magnetometer`. A scene is checked against the device only when it is about to
run. A scene that copes without some hardware leaves it out of `requires` and
asks `state.capabilities.has(name)` instead.

Scenes switch only by rebooting the device into the next one. An **Overlay**
covers a scene for a while and hands it back intact.

The meaning of each term, the versioning rules, and the reasoning behind these
choices are in [`GLOSSARY.md`](GLOSSARY.md) and the ADRs in
[`docs/adr/`](docs/adr/), notably
[ADR-0003](docs/adr/0003-settings-are-declared-as-data-and-checked-at-scan.md)
(Settings),
[ADR-0004](docs/adr/0004-capabilities-are-checked-when-a-scene-is-about-to-run.md)
(Capabilities) and
[ADR-0005](docs/adr/0005-scenes-switch-only-by-reboot.md) (scene switching).

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
