# A driver library is imported only by the part that builds it

`CircuitPythonParts` imports `board`, `busio`, `digitalio` and `microcontroller` at module level, because every build needs them. Every per-component driver library (`adafruit_is31fl3741`, `neopixel`, `adafruit_lis3dh`, `adafruit_mmc56x3`, `adafruit_drv2605`, `pulseio`, the audio stack, `adafruit_rfm69`, `sdcardio`) is imported inside the part that builds its component. An adapter module that imports a library at load time, such as `Rfm69RadioTransport` or `SdCardStorage`, is itself imported only from inside its part. So a prop whose `aura-device.json` doesn't declare a component, or declares it with `enabled: false`, boots without that component's library on the board.

Spec #688 made this rule (built by #690). Props are built from different subsets of parts, and before it the device builder imported several driver libraries at module top. A prop with no matrix, no audio and no haptics still wouldn't boot unless every one of those libraries was installed.

## Considered Options

- **Import every driver library at module level.** Simplest to read. Rejected: a minimal prop has to carry libraries for hardware it doesn't have.
- **Import inside the part that builds the component (chosen).** A prop ships only the libraries its config uses, and turning a component off with `enabled` also drops its library.

## Consequences

- A declared, enabled component whose library is missing fails the build like any other declared part that can't be built (ADR-0014).
- Checker-only imports of the same libraries live under `TYPE_CHECKING`, so annotations still name the real driver types.
