# Embedded Python: aura rules

aura's additions to the `code-quality` skill's `embedded-python.md` reference. Apply both; where they differ, this file wins.

## Native Code (`@micropython.native`)

Production code compiles to bytecode only: `@micropython.native` and `-X emit=native` are unsupported while the project targets the RP2350. Spec #1235 measured both on an RP2350 board with 8 MB PSRAM: no single function on the per-pixel path (merge strategies, palette lookup, layer renderers, `EffectManager.update`) gained more than ~3 % FPS, and compiling every module native made frames 24–30 % slower.

## Checker-only imports go under a bare `TYPE_CHECKING = False`

This is the one sanctioned `TYPE_CHECKING` idiom. Declare the name at module level after the runtime imports (ruff's E402 rejects imports below an assignment), never import it:

```python
from engine.packs import PackRegistry

TYPE_CHECKING = False

if TYPE_CHECKING:
    from collections.abc import Callable
    from typing import Final

    from engine.scene import SceneLocalRegistry
```

The device never imports `typing` and skips the block. mypy treats the name as true, so the guarded imports are still checked. Don't use `try: from typing import TYPE_CHECKING / except ImportError: TYPE_CHECKING = False`: mypy rejects the fallback assignment ("cannot assign to final").

Don't import `typing` or `collections.abc` inside a `try:` block either (`try: from typing import Final / except ImportError: pass`). `engine/tests/test_checker_only_imports.py` fails on that form in any module outside a `tests/` directory and names the file and line. A module whose annotations name a guarded import needs `from __future__ import annotations`: CPython before 3.14 evaluates module-level annotations such as `NAME: Final = 1` eagerly.

## Long Strings

mpy-cross rejects adjacent string literals split across lines, so ruff's ISC002 rejects them in device code (`allow-multiline = false` in `pyproject.toml`). To break a long string, join the pieces with an explicit `+` inside parentheses:

```python
raise ValueError(
    f"audio pin {name} is not a pin on this board; "
    + "name one of the board pins listed in device.json under audio"
)
```

## Generics are checker-only subclasses (ADR-0007)

The device can't run `Generic`, so put the implementation in a plain runtime class and declare the generic as a subclass of it under `TYPE_CHECKING`. Re-declare only the signatures that mention the type parameter, and bind the public name to the runtime class under `else:`:

```python
class _StateSlotBase:
    def __call__(self, state: GameState) -> object: ...  # the real body


if TYPE_CHECKING:
    from typing import Generic

    class StateSlot(_StateSlotBase, Generic[T]):
        def __call__(self, state: GameState) -> T: ...

else:
    StateSlot = _StateSlotBase
```

Never put the implementation under `else:`. mypy treats that branch as unreachable and doesn't check it.

## Stub Defects

This replaces the skill's advice to leave board-attribute diagnostics visible.

When `circuitpython-stubs` is wrong about a call the firmware accepts, suppress the error at the call site with `# type: ignore[code]` and a reason comment that links an upstream adafruit/circuitpython issue reporting the defect. File the issue first: the `shared-bindings` file and line, the wrong and corrected signatures, and evidence that the firmware accepts the call. Never patch or shadow the stub with a local copy.

```python
# Stub defect: circuitpython-stubs marks WaveFile's buffer required, but the
# firmware treats it as optional. https://github.com/adafruit/circuitpython/issues/<n>
wave = audiocore.WaveFile(f)  # type: ignore[call-arg]
```

A stub-defect ignore without a linked upstream issue fails review. When the fixed stubs ship, the version bump removes the ignore (mypy reports it as unused).

## CircuitPython Handles

Annotate a CircuitPython handle (a pin, bus, `pulseio.PulseIn`, `rp2pio.StateMachine`, a driver object) with its stub type, never `object`. Import the type under `if TYPE_CHECKING:` so the device pays nothing at runtime:

```python
TYPE_CHECKING = False

if TYPE_CHECKING:
    import pulseio


class PulseInReader:
    def __init__(self, pulsein: pulseio.PulseIn) -> None: ...
```

Quote the annotation when the module has no `from __future__ import annotations`. A port that passes a handle through without using it (as `DeviceParts` does a bus) declares a checker-only `Any` alias for it, which each adapter narrows.

## Review checklist additions

- [ ] `TYPE_CHECKING` declared as a bare module-level `TYPE_CHECKING = False`, never imported from `typing`
- [ ] CircuitPython handles annotated with their stub type, imported under `if TYPE_CHECKING:`, never `object`
- [ ] Every stub-defect `# type: ignore[code]` links its upstream adafruit/circuitpython issue; no local copy of a stub `circuitpython-stubs` provides
