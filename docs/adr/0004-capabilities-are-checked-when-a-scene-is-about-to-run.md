# Capabilities are declared as data and checked when a scene is about to run

A scene and each **Rule pack** list the **Capabilities** they cannot be played without, in a `requires` list in `scene.json` and the pack's **Pack manifest**. The **PackCatalog** scan checks that every name is in the vocabulary, but it never compares them with the device. That comparison happens only for the scene about to run: at boot, and on every transition into a scene. It is made against the Capabilities **Device assembly** actually built, never against `DeviceConfig`.

Before this change a scene's hardware needs were implicit, and a mismatch surfaced only during play, in four different ways: Red Light Green Light without an accelerometer skipped its motion checks, so motion could never lose; Tag without IR raised `ValueError` on the first shot; a rule sending radio without a radio silently did nothing; and Return to lobby on a one-button prop could never fire.

## Considered Options

- **Check every installed scene at scan, as ADR-0003 does for Settings.** Errors surface earliest, but a card carrying scenes for several prop shapes would stop a lesser prop from booting at all, even though the scene it boots into fits.
- **Check against `DeviceConfig`.** Simpler to read, but a component that is declared and then fails to build (its bus can't open) would pass the check and fail during play, which is the bug this removes.
- **Check the scene about to run, against what was built (chosen).** A card can carry scenes for any prop. The one scene that runs is guaranteed its hardware.

## Consequences

- At boot, a **Persisted scene** the device can't run is skipped in favour of the flash `default_scene` and logged, but left on the card, so a card moved back to a fuller prop resumes where it was. Boot stops with `MissingCapabilityError` only when no candidate fits.
- A transition into a scene the device can't run raises before anything is persisted or reset. Rules can ask whether the device can run a scene, so a lobby offers only the scenes this prop can play.
- `send_ir` and `send_radio` now behave the same on missing hardware: both raise `MissingCapabilityError`. `send_radio` previously did nothing. A scene that copes without some hardware leaves it out of `requires` and asks `state.capabilities.has` before using it.
- Capabilities are named by component and by the names rules use (button labels, IR emitters), never by bus or part, so packs stay independent of how a prop is wired. Pixels, audio and haptics are not Capabilities, because effects already cope without them.
- A Rule pack's `requires` is part of its versioned interface. Adding a Capability is a major bump, and removing one is a minor bump.
