# Python Docstrings

Formatting reference for Python docstrings. The decision of *whether* a symbol needs a docstring at all, along with the "naming → test → comment" ordering, lives in the `comments` skill; this file covers only *how* to format the ones that survive that test.

## Class Docstrings

Open with what the class is **for** and why it matters to the caller, not a description of its internal mechanics.

Follow with technical contracts using concise bullet lists under named sections. Name sections after the actual contract being expressed, since these vary by domain. Examples from an animation library:

- **Update model**: when and how state is mutated
- **Sampling model**: how values are read or queried
- **State ownership**: who owns, creates, and disposes of state

```python
class Ripple:
    """Produces an expanding ring animation centered on a point.

    Useful for highlighting events or drawing attention to a position
    in a pixel strip or grid.

    Update model:
      - Call ``update(t)`` once per frame with the current timestamp.
    Sampling model:
      - Call ``value(pos)`` per pixel after each ``update`` call.
    State ownership:
      - Owns internal phase state; safe to copy by value.
    """
```

## Method Docstrings

One line is correct when the signature already conveys the _what_. Expand only to describe:

- Non-obvious **ordering** constraints (e.g., must call X before Y)
- **Return semantics** that aren't clear from the type annotation
- **Side effects** that affect external state

```python
def update(self, t: float) -> None:
    """Advance animation state to timestamp ``t``."""

def value(self, pos: int) -> float:
    """Return brightness at ``pos`` for the current frame, in [0.0, 1.0]."""
```

### Growing into `Args:` / `Returns:` / `Raises:`

Once a method takes more than one or two parameters, or a parameter's meaning or constraints aren't obvious from its name and type alone, drop into Google-style sections rather than cramming everything into the summary line:

```python
def validate_band_map(bands: dict[str, range], context: str) -> None:
    """Validate that all scope keys are valid and bands do not overlap.

    Args:
        bands: Mapping of scope key → range.
        context: Label used in error messages (e.g. ``"pixels[0].scope_rows"``).

    Raises:
        ValueError: If a key is invalid or two bands overlap.
    """
```

**An `Args:` entry documents only its own parameter, never the method's broader contract or side effects.** If a note doesn't answer "what is this argument, what does it mean, what must it satisfy," it belongs in the summary line or a named section instead, not smuggled into the nearest parameter's entry.

```python
# WRONG: is_busy() behavior is a method-level side effect, not a fact about
# the `durations` parameter
def write_pulses(self, durations: list[int]) -> None:
    """Send *durations* via the PulseOut hardware.

    Args:
        durations: Sequence of integer pulse durations (µs), alternating
            mark/space, starting with a mark. The underlying
            ``pulseio.PulseOut.send`` call blocks until transmission
            completes. ``is_busy()`` reports ``True`` for the duration of
            the call.
    """

# RIGHT: the side effect moves into the summary, Args: stays scoped to the parameter
def write_pulses(self, durations: list[int]) -> None:
    """Send *durations* via the PulseOut hardware.

    Blocks until transmission completes. ``is_busy()`` reports ``True`` for
    the duration of the call.

    Args:
        durations: Sequence of integer pulse durations (µs), alternating
            mark/space, starting with a mark.
    """
```

## `__init__` Docstrings

Do **not** add a docstring to `__init__` when the class docstring already describes construction parameters. Duplicate documentation drifts out of sync.

## Symbol References

Use `double backticks` for values that aren't cross-references to another class or method, including:

- Parameters and fields: `t`, `pos`
- Literals that would otherwise read as bare words: `None`, `True`, `False`
- The method's own name when referring to itself within its own docstring: `update()`

```python
# Correct
"""Returns ``None`` if the buffer is empty."""

# Incorrect
"""Returns None if the buffer is empty."""
```

Use the Sphinx cross-reference roles `` :class:`Name` `` and `` :meth:`name` `` instead when referencing another class or method by name, so the reference resolves to a link in generated docs rather than reading as plain text:

```python
# Correct: this is a reference to another type/method, not a value or literal
"""Transmits IR payloads through a :class:`PulseWriter`.

Starting a write calls :meth:`IrTransmitGate.begin_transmit`, then
:meth:`PulseWriter.write_pulses`.
"""

# Incorrect: loses the cross-reference
"""Transmits IR payloads through a ``PulseWriter``."""
```

## Checklist

- [ ] Class docstring leads with user-facing purpose, not mechanics
- [ ] Technical contracts are in named bullet sections
- [ ] Method docstrings are one line unless non-obvious behavior needs explanation
- [ ] Multi-parameter or non-obvious signatures use `Args:`/`Returns:`/`Raises:` blocks, and each `Args:` entry documents only its own parameter
- [ ] Plain values and literals use `double backticks`; references to other classes/methods use `` :class:`Name` ``/`` :meth:`name` ``
- [ ] No `__init__` docstring if class docstring covers parameters
