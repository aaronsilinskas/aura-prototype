# Settings are declared as data and checked when the catalog is scanned

A scene's and a pack's **Settings** are declared as data: in `scene.json`, and in the pack's **Pack manifest** (`rules.json` / `effects.json`, which replaces `version.txt`). Each declaration gives a name, a type and an optional default. Each pack reference in a scene can carry **Setting overrides** for that pack. The **PackCatalog** scan checks every override against the declarations and resolves every Setting before boot continues.

Before this change, a knob was stated in three places that nothing tied together:
- a seed key in `scene.json`'s `initial_data`;
- a `state.get(key, default)` in the scene's Scene Config;
- a config field, sometimes under a different name.

A mistyped key silently read as the default, and a seeded key that nothing read went unnoticed (`hw_mode`). Seeds also shared one flat `GameState` store with runtime game data.

## Considered Options

- **Declare each Setting in Python, in the Scene Config module, and check when the scene starts.** This keeps typing and named constants. But the catalog imports item code lazily, at first use, so the scan can't read a Python declaration on a device without importing every installed scene's code at boot. Errors would then surface at scene start instead of at scan.
- **Have the scan import each scene's settings module.** This gives scan-time errors, but it breaks lazy loading and costs RAM at boot for scenes that never run.
- **Declare Settings as data in manifests and `scene.json` (chosen).** The scan reads JSON it already opens, so every override is checked before boot continues, with no code imported. A default lives only in its declaration, and Python never restates it.

## Consequences

- Defaults that were Python constants (`MOTION_EMA_ALPHA`, `GRAVITY_LOWPASS_BETA`) move into JSON. A constraint between two Settings is checked by the Scene Config that derives from them.
- Types are limited to what JSON can state and the scan can check cheaply: `int`, `float`, `bool`, `str`, and `list` (top level only). Deep structure is still validated by pack code.
- Rules read Settings through a read-only view, by namespace (`scene` or the pack's name) and Setting name, never through `GameState`'s `get` / `set`.
- A pack's Settings are part of its versioned interface:
  - **Minor bump:** adding a Setting that has a default.
  - **Major bump:** adding a required Setting, or removing, renaming or retyping a Setting.
