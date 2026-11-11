# Embedded Python (CircuitPython / MicroPython)

Platform-specific rules for Python that runs on microcontrollers, LED strips, or other constrained hardware, where GC pauses, memory allocations, or CPU limits matter. Load this alongside the `code-quality` skill whenever writing or reviewing CircuitPython/MicroPython code, animation loops, per-frame update logic, per-pixel sampling, or any hot path, even if the user doesn't say "CircuitPython" explicitly.

The general quality bar (readability, public-API discipline, type coverage) lives in the `code-quality` skill; this file adds the embedded constraints on top and, where they conflict, they win.

## Hot Path Definition

A hot path is any code that executes many times per second in a tight loop, where even small per-iteration costs compound into GC pressure or visible stutter. Common examples include:

- Animation update loops that run every frame (e.g., 30-60 times per second)
- Per-pixel sampling functions that run for every pixel on every frame

Everything else (construction, one-time initialization) is a cold path and can use normal Python patterns freely.

## Memory Rules (Hot Paths)

**Never allocate inside a hot path** unless genuinely unavoidable:

```python
# Bad: allocates a list every frame
def update(self, state, timer):
    values = [x * 2 for x in self.buffer]  # comprehension allocates

# Good: mutate in place
def update(self, state, timer):
    for i in range(len(self.buffer)):
        self.buffer[i] = self.buffer[i] * 2
```

Specific patterns to avoid in hot paths:

- List/dict/set literals or comprehensions
- `lambda` or closure creation
- Object instantiation (`Foo(...)`)
- String formatting (`f"..."`, `"".join(...)`)
- Exception raising for control flow

## Loop Rules (Hot Paths)

Always use plain `for` loops. List comprehensions and generator expressions allocate:

```python
# Bad
total = sum(x for x in buffer)

# Good
total = 0.0
for i in range(len(buffer)):
    total += buffer[i]
```

Keep branch logic minimal inside loops. Pre-compute bounds and constants outside the loop:

```python
# Pre-compute outside the loop
inv_span = 1.0 / span
lower = padding
upper = 1.0 - padding

# Lean inner loop
for i in range(pixel_count):
    pos = i / pixel_count
    if pos < lower or pos > upper:
        out[i] = 0.0
    else:
        out[i] = shape_func((pos - lower) * inv_span)
```

## Floating Point Rules

Avoid repeated expensive computations. Hoist constants out of loops and cache `math.*` calls:

```python
# Bad: recomputes tau every pixel
def shape(position):
    return math.sin(freq * position * 2.0 * math.pi)

# Good: capture tau once at definition time
tau = 2.0 * math.pi
def shape(position):
    return math.sin(freq * position * tau)
```

Prefer multiply over divide when the denominator is fixed. In hot paths, always use `x * x` instead of `x ** 2`. The `**` operator has meaningful overhead on embedded devices even with compile-time constant exponents.

## Native Code (`@micropython.native`)

`@micropython.native` compiles one function to machine code, at a cost in flash and RAM. A function earns it only by a measured gain:

- **Keep rule:** decorate a function only when median FPS rises by at least 5 % at 60 pixels, against the undecorated control run in the same session, on at least one benchmark scene (`tag`, `element_browser`) and drops on neither. Revert a decoration below the bar. 144-pixel numbers are recorded for information only.
- **The PR records** the median FPS of the control and the candidate, per scene and pixel count; the `.mpy` size change; and `gc.mem_free()` at scene start. Read `gc.mem_free()` with a throwaway, uncommitted print after `build_scene_boot` in `app/scene_runtime.py`: no timing or reporting helper is committed (#1180).
- **Spelling:** `import micropython`, then `@micropython.native`. `mpy-cross` recognizes the decorator only by that exact spelling, so `from micropython import native` never compiles native. CPython has no `micropython` module, so the first decoration also adds a host-only `micropython.py` at the repo root, never deployed, for tests and mypy. #1239 built one and withdrew it unused.
- **Per function only:** whole-module native (`-X emit=native`) and `@micropython.viper` stay out of production code.

Measure on an RP2350 board with 8 MB PSRAM under deploy-watch:

1. Back up CIRCUITPY's `aura-device.json`.
2. Set every enabled NeoPixel strip's `count` to 60, then to 144, and spread its `scope_pixels` bands evenly over the new count. Effects render only scope pixels, so raising `count` alone adds no per-pixel work. The matrix stays out.
3. In one session, run the undecorated control, then the decorated candidate: `tag` and `element_browser` (`--scene`, `--seconds 75`) with the `debug` pack's `fps_logging_enabled` Setting on. `element_browser`'s `scene.json` sets it. For `tag`, add the `debug` pack reference with that Setting to its `scene.json` for the run only.
4. Take the median of the last 10 three-second `FpsLoggerRule` windows (`FPS:` lines) per scene and count. The first ~20 s run slower. `tag` drifts ~4 % between runs, so run it three times per side and use the median of the run medians; a recorded baseline can't stand in for the same-session control.
5. Restore the backup, revert the `tag` edit and redeploy.

## CircuitPython and MicroPython Compatibility

This reference targets the **latest stable releases** of CircuitPython and MicroPython. Do not flag features as unavailable unless they are absent from current releases.

Minimize and isolate CircuitPython-specific dependencies so the same code can run on MicroPython and other environments. Avoid scattering platform-specific imports or calls throughout modules; contain them at the boundary.

**Built-in generic subscripts are supported:**

`list[X]`, `dict[K, V]`, `tuple[X, ...]`, and `X | Y` union syntax work at runtime in latest releases. Use them freely in annotations, with no string quoting or `try/except` guard needed.

**Guard `typing` and `collections.abc` imports:**

Advanced `typing` constructs and `collections.abc` abstractions are still absent or incomplete. Guard any imports from these modules:

```python
try:
    from collections.abc import Callable
    from typing import Any, TypeAlias
except ImportError:
    pass  # Not available on all embedded runtimes
```

**Checker-only imports go under a bare `TYPE_CHECKING = False`:**

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

**Generics are checker-only subclasses (ADR-0007):**

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

**Module count matters.** Import cost is paid at startup on-device. Keep related logic in the same file rather than splitting into many small modules when startup latency is a concern.

**Still unavailable on latest CircuitPython / MicroPython:**

- `dataclasses`
- `collections.defaultdict`, `functools`, `itertools`
- `typing.TypeVar`, `typing.TypeAlias`, `typing.Protocol`, `typing.Generic`
- `collections.abc` (most abstractions including `Callable`)
- Large standard library modules

Prefer explicit, simple data structures (`list`, `dict`, plain classes with `__slots__`) over convenience wrappers.

## Type Hint Exceptions

The `code-quality` skill requires type hints on all parameters and returns. On embedded targets, use narrowly-scoped exceptions when a concrete runtime constraint makes precise typing impractical, for example:

- Board/runtime-provided objects that have incomplete or incorrect stubs
- CircuitPython-specific APIs where stub types conflict with known runtime behavior
- Dynamic callback/plugin-style call sites where strict callable signatures are not representable without harming portability

When using an exception, still annotate with the best available fallback type and add a brief code comment explaining why a precise type is not possible in that location.

## Stub Defects

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

## Class-Level Constants

Annotate all class-level constants with `Final` to prevent accidental reassignment. Omit the type parameter, since Pylance infers it from the assigned value:

```python
try:
    from typing import Final
except ImportError:
    pass

class MyConfig:
    MAX_PIXELS: Final = 117
    DEFAULT_BRIGHTNESS: Final = 0x33
```

`Final` is part of the standard `typing` module and is respected by Pylance, mypy, and Pyrefly. The import must be guarded with `try/except ImportError` because `typing` may be absent on some embedded runtimes. The annotation itself must **never** be quoted. String-quoting `Final` is unnecessary for CircuitPython.

## State Object Lifecycle

Initialize state once and mutate in place on every subsequent frame. Use a guard to distinguish first-run from update:

```python
def update(self, state, timer):
    if state is None:
        state = _Data(self.buffer_count)  # allocate once
    # mutate in place, no allocation
    state.phase = (state.phase + 1) % self.period
    return state
```

## `__slots__` for State Objects

Use `__slots__` on objects that are created per-instance and live for the duration of the animation. This lowers per-instance memory and speeds attribute access:

```python
class _Data:
    __slots__ = ("offset", "buffer", "phase")

    def __init__(self, buffer_count: int):
        self.offset = 0.0
        self.buffer = [0.0] * buffer_count
        self.phase = 0
```

## Checklist

- [ ] No list/dict/set allocation inside hot-path loops
- [ ] No comprehensions in hot paths, only plain `for` loops
- [ ] No exceptions used for control flow
- [ ] Constants and math calls hoisted outside inner loops
- [ ] State objects initialized once via a guard, mutated in place on subsequent frames
- [ ] `__slots__` used on long-lived per-instance state objects
- [ ] `typing` and `collections.abc` imports guarded with `try/except ImportError` (advanced constructs such as `TypeVar`, `Protocol` and `Callable` are still absent from latest releases)
- [ ] `TYPE_CHECKING` declared as a bare module-level `TYPE_CHECKING = False`, never imported from `typing`
- [ ] CircuitPython handles annotated with their stub type, imported under `if TYPE_CHECKING:`, never `object`
- [ ] Every stub-defect `# type: ignore[code]` links its upstream adafruit/circuitpython issue; no local copy of a stub `circuitpython-stubs` provides
- [ ] Class-level constants annotated with `Final` (unquoted, no type parameter; import guarded with `try/except ImportError`)
- [ ] No imports from unavailable stdlib modules
- [ ] Every `@micropython.native` (spelled exactly so, after `import micropython`) meets the keep rule against a same-session control, and its PR records the FPS numbers, `.mpy` size change and `gc.mem_free()`
