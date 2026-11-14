# The device state store stays general; the Persisted scene is one client of it

`DeviceStateStore` stays a general key/value store over the card's `aura-state.json`, not a store for the **Persisted scene** alone. Games will increasingly keep their own state there across a Reboot (inventory, level, player ID). So the Persisted scene record is one client of the store: a `PersistedScene` module that alone names its keys, under the reserved `persisted_scene.` prefix, and makes each change in one atomic `update`.

Today only the Persisted scene keys live in the file, so the store looks like a seam with one adapter, which is a hypothetical seam. An architecture review will be tempted to fold the store into `PersistedScene`. That was considered and rejected in the 2026-11 architecture review, because the second client, game data, is planned. Spec #742 also built the store as general cross-reboot persistence.

## Consequences

- Game data must not use the `persisted_scene.` prefix. Its own layout (a key prefix, a nested map or a separate file) is decided by the spec that introduces it.
- Older cards' unprefixed `scene` and `return_to` keys are inert; there is no migration.
