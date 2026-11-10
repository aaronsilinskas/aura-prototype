# Effect verbs are typed, matched by identity, and declared by the sight modality that emits them

An **EffectVerb** is a value, not a string. `EffectVerb.START` and `EffectVerb.STOP` belong to the engine. Each custom verb is declared once, on the `EffectPixels` class that emits it (`LightningEffect.STRIKE`, listed in its `VERBS`). `EffectAudio` and `EffectHaptic` accept only `EffectVerb` keys, and verbs compare by identity. When an effect is built, `EffectManager` rejects any `clips` or `patterns` key the effect can never emit, and any `STOP` clip. This extends ADR-0002: a misspelled clip *name* already failed at `set_effect`, but a misspelled verb *key* played nothing and raised nothing. A haptic pattern on a wrong key also gave no buzz, which looks the same as a weak motor on hardware.

## Considered Options

- **String keys, checked at build against declared verb names.** This catches typos at `set_effect`, but nothing stops a hand-typed key, and authors get no list of what an effect can emit.
- **Declare verbs as data in `effects.json`, like Settings (ADR-0003).** Browsable without reading code, but the JSON and the emitting `notify_listeners` call sit in different files and can drift: the same typo problem, moved. Data is keyed by effect name, so a scene-local wrapper that reuses a pack effect's pixels (Tag's `warning_pulse` over `basic.pulse`) would have to restate the inherited verbs in `scene.json`. The scan also gains nothing, because the keys to check live in Python that is only imported at build time.
- **Typed verbs, declared on the emitting class (chosen).** A string key fails when the module is imported, and a misspelled constant raises `AttributeError`. Wrappers inherit the declaration through the pixels object they reuse. The verb's spelling lives once, next to the code that emits it.

## Consequences

- Identity matching means a hand-made `EffectVerb("strike")` is not `LightningEffect.STRIKE`. Authors must import the emitter's constant, which is also how they discover what it emits.
- Only the sight modality can emit custom verbs. An effect without pixels has `START`/`STOP` only.
- Verbs reach outputs, never rules. Rules time game logic with their own timers, Settings and game events, so an animation's speed never changes when the game advances. Game-rule `Event`s are not `EffectVerb`s; rules match those by class.
- An effect pack's declared verbs are part of its versioned interface. Adding one is a minor bump, removing or renaming one a major bump.
