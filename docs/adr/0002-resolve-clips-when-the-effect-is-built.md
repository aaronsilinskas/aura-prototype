# Clip names are resolved when the effect is built, and hardware never resolves names

`EffectManager` resolves every clip an effect declares through the **Active scene namespace** when the effect is built, inside `set_effect` / `add_effect`. Each `EffectEvent` then carries the **Resolved clip** for its verb, and audio outputs play the path they are given. Previously each audio output held an `AudioRegistry` and turned a clip name into a path while handling an event mid-tick. That made hardware assembly build and hand out a name-resolution object. A misspelled clip failed inside an output, far from the rule that chose it, and a clip on a rarely fired verb (`"peak"`) went unchecked until that verb first fired. It also meant the `scene.` / `<pack>.` routing, the declared-pack gate and their error wording existed twice, once for effects and once for clips.

## Considered Options

- **Keep a lookup in each output, but share the routing code.** Removes the duplication, but hardware still holds a name-resolution object, and clip typos still fail mid-tick.
- **Resolve lazily per verb in `EffectManager`.** Keeps hardware path-only, but a rarely fired verb's typo still hides until play.
- **Resolve every declared clip at build time (chosen).** Errors surface at the rule's `set_effect`, hardware deals only in paths, and one module owns all name routing.

## Consequences

- This deliberately reverses the earlier stance that sound overlays were a "separate seam, separate concern" from effects. What both received at a transition was the same active-scene view; only the leaf lookup differed.
- `EffectEvent` carries a payload (`clip`) that is not part of its identity: equality and hashing stay on `(pack, name, verb)`.
- import-linter forbids hardware from importing the namespace module, so resolution cannot creep back into outputs.
- Test helpers that take clip names (`Simulation.is_playing`, `clip_length`) resolve them against whichever scene is active when they are called.
