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

For board-provided attributes and pin objects (for example `board.TX`, `board.RX`) where stubs may be incomplete, prefer leaving diagnostics visible instead of adding inline `# pyright: ignore[...]` comments. Only suppress these diagnostics when explicitly requested by the user or required by project policy.

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
- [ ] Class-level constants annotated with `Final` (unquoted, no type parameter; import guarded with `try/except ImportError`)
- [ ] No imports from unavailable stdlib modules
