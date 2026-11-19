# Hardware is built from config, never probed

The **Device assembly** builds a component only when `aura-device.json` declares its section and the section is enabled. It never probes a bus to find out what is fitted. A declared, enabled component that can't be built (its chip doesn't answer, its bus isn't there, its library is missing) fails the build. Absence is said by omitting the section or setting `enabled: false`, never by a probe that quietly finds nothing.

Spec #688 removed the last probes (#691). Before it, the LIS3DH accelerometer and the DRV2605 haptics motor were attached by physical presence: the builder probed the I2C bus for them on every boot whatever the config said, and a failed probe logged a warning and built nothing. Every other component was already config-gated. The spec made the config the single source of truth for what a prop has, so a miswired or dead part fails loudly instead of disappearing.

This differs from ADR-0004. That ADR checks a scene's **Required capabilities** against what the Device assembly built. This one decides what gets built in the first place.

## Considered Options

- **Probe for optional parts and build what answers.** No config needed for those parts, but a dead or miswired chip looks the same as an absent one.
- **Build from config and fail on a declared part that can't be built (chosen).** A prop's hardware is what its config says, and a fault in a declared part stops the boot with the part named.

## Consequences

- A prop with an accelerometer or haptics motor must declare it (`"accelerometer": {}`, `"haptics": {}`).
- The **Component enabled toggle** turns a component off without deleting its section. A disabled section is still validated in full, and its library is not imported (ADR-0013).
- A bus needs no section of its own. A device that names no bus joins the `default` bus, which is the board's own bus unless `default` is declared, and a bus is opened only when an enabled device names it (**Named bus**).
- The **Simulated device** builds through the same Device assembly, so it builds, skips and rejects a config the same way the physical device does.
