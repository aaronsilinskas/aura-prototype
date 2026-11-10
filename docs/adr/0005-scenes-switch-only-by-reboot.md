# Scenes switch only by reboot; an overlay covers the scene, it does not switch it

A device changes scene only by **Reboot**: the target is persisted, the device resets, and the new scene boots clean, with its own IR codec and setup. Rules get no in-process `load`. A switch inside the running program would have to carry everything a scene sets up on the device, including the IR codec, which is applied once at boot. Getting that wrong runs a game on the wrong wire-frame, all to save a reboot at a moment players already expect a change.

Pause, menus and status screens are **Overlays**: a scene laid on top of the running one, which it suspends with its game state and game time intact and gives back on `pop`. Rebooting for these would be too slow and would lose the game. An overlay is not a scene switch: it runs on the covered scene's IR codec, whatever it declares, so a game's own traffic (including whatever message unpauses it) keeps working under a shared pause scene.

## Considered Options

- **One in-process switch that carries all per-scene setup** (codec, namespace, merge strategies), used for both changing scene and covering one. Rejected: it would mean re-applying the codec while running, and changing scene gains nothing over a reboot.
- **Pause as a phase of each game.** Rejected: entering it runs the current phase's `on_exit`, resuming restarts that phase from zero, rules not gated to a phase keep running, and it can't be shipped once in a shared pack.
