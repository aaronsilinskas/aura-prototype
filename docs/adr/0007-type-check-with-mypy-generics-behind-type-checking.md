# Type-check with mypy; generics live behind `TYPE_CHECKING`

mypy is the repo's type checker, blocking in CI and pre-commit. We compared five checkers on the same scope: production packages, default strictness, the same CircuitPython stubs. mypy found the most errors, 139 against 91–111, and its extras were mostly real gaps. The biggest was `StateSlot`, which isn't generic. pyright, basedpyright and ty quietly inferred an unknown type for it, which left every rule's game-state access unchecked. mypy reported it.

CircuitPython can't run generics. It has no `typing` module, and `class X[T]:` is a `SyntaxError` in `mpy-cross` 10.3.1. MicroPython's typing work (micropython/micropython#15911) lists user-defined generics as unsupported. There is no evidence that CircuitPython 11 will support class-level generics either. So a generic interface is declared only for the checker, under `if TYPE_CHECKING:`, and the plain runtime class sits beside it in the same module under `else:`. Modules use a bare `TYPE_CHECKING = False`, not a `try: from typing import TYPE_CHECKING` fallback. mypy still treats the name as true, and the device never imports `typing`.

## Considered Options

- **pyright / basedpyright.** These match what VS Code's Pylance shows, but they found fewer errors and missed the `StateSlot` gap. pyright's PyPI wrapper also downloads Node.js.
- **pyrefly, ty.** Fastest, at 0.3s. ty is beta, and both missed the `StateSlot` gap.
- **Runtime enforcement instead of a checker.** Spec #1199 had to reject non-`EffectVerb` keys with a runtime `TypeError` because nothing checked types. A checker catches this class of mistake before deploy.

## Consequences

- Pylance (pyright) diagnostics in the editor can disagree with mypy. mypy is the source of truth.
- Code shaped for mypy's inference, such as checker-only generic declarations, may need reworking if the checker ever changes.
- If CircuitPython gains `typing.Generic`, the `TYPE_CHECKING` split can collapse into one class. Until then, a generic is always two declarations kept in step.
