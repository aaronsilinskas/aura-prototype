# Ports are plain base classes, not `typing.Protocol`

A port that device code implements is a plain base class whose methods raise `NotImplementedError`: `PulseReader` and `PulseWriter`, `RadioTransport`, `VoiceSink`, the SD-sync `Transport`, `PolledPart`, `DeviceParts`, `MergeStrategy`, and the engine's `EffectControls`, `SceneControls` and `NetworkControls`. Every live adapter and every test fake subclasses its port explicitly. CircuitPython has no `typing` module (ADR-0007), so a port that exists at runtime can't be a `typing.Protocol`. An explicit subclass also lets mypy check each adapter's and fake's overrides against the port where the class is defined. `docs/standards/mocking-python.md` relies on this: a fake subclasses the real base and overrides only what its test needs, and a changed port signature breaks the fake under mypy.

## Considered Options

- **Duck typing with no base class.** Nothing at runtime to import. Rejected: mypy has no type to check an adapter against, and a missing method fails only when called.
- **A `Protocol` declared only under `TYPE_CHECKING`,** as ADR-0007 does for generics. mypy would check adapters structurally and the device would carry no base class. Not recorded why this wasn't taken for ports. The likely reasons, to be confirmed: the pattern predates the `TYPE_CHECKING` idiom, and under a Protocol every fake would have to implement every method to type-check, where a base class lets it inherit the rest.

## Consequences

- Checker-only Protocols are still used where nothing implements them at runtime: a `TypeVar` bound (`_Gated` in `device_assembly`) or a structural type that avoids an import edge (`_Rule` in `engine/state.py`). They are not ports.
- A method a subclass forgets to override fails with `NotImplementedError` when called, not when the class is built. mypy does not flag it.
