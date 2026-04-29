from __future__ import annotations

try:
    from collections.abc import Iterable
    from typing import Any, TypeVar

    T = TypeVar("T")
except ImportError:
    pass  # No typing support on CircuitPython yet

from effects.shape import EffectShapeFunc, Shape

_MISSING = object()


def run_step_updates(
    steps: list[EffectStep],
    step_index: int,
    state: EffectState,
    timer: EffectTimer,
) -> int:
    """Update a list of ``EffectStep`` instances sequentially until all steps
    have been processed once or a step stops the sequence.

    Each step's ``update`` method returns ``True`` when the step should advance
    to the next step. This helper keeps advancing until the active step returns
    ``False`` or all steps were processed once. Returns the index of the step
    that should remain active after this call.
    """
    step_count = len(steps)
    if step_count == 0:
        return step_index

    steps_processed = 0
    while steps_processed < step_count and steps[step_index].update(state, timer):
        step_index = (step_index + 1) % step_count
        steps_processed += 1

    return step_index


class SharedStateKey:
    """Marker base class for shared state keys stored in ``EffectState``."""


class EffectState:
    """Holds all mutable animation state so one ``Effect`` instance can drive
    multiple independent animations simultaneously.

    State ownership:
    - Per-step data is keyed by step instance via ``get_step_data`` / ``set_step_data``.
    - Shared data is keyed by ``SharedStateKey`` and accessible across steps
      (e.g. velocity shared between rotate and accelerate steps).
    """

    def __init__(self):
        self._step_indices: dict[Effect, int] = {}
        self._step_data: dict[EffectStep, Any] = {}
        self._shared_data: dict[SharedStateKey, Any] = {}

    def get_step_index(self, effect: Effect) -> int:
        """Return the active step index for an effect, defaulting to ``0``."""
        return self._step_indices.get(effect, 0)

    def set_step_index(self, effect: Effect, index: int) -> None:
        """Set the active step index for an effect."""
        self._step_indices[effect] = index

    def get_step_data(self, step: EffectStep, expected_class: type[T]) -> T | None:
        """Return state previously stored for a step, if any.

        ``expected_class`` is accepted for API readability, but runtime type
        checking is intentionally omitted to keep lookups lightweight.
        """
        return self._step_data.get(step)

    def set_step_data(self, step: EffectStep, value: Any) -> None:
        """Store mutable state associated with a specific step instance."""
        self._step_data[step] = value

    def remove_step_data(self, step: EffectStep) -> None:
        """Remove state associated with a specific step, if present."""
        self._step_data.pop(step, None)

    def get_shared_data(self, key: SharedStateKey, expected_class: type[T]) -> T | None:
        """Return shared state for a key, if any.

        ``expected_class`` is accepted for API readability, but runtime type
        checking is intentionally omitted to keep lookups lightweight.
        """
        return self._shared_data.get(key)

    def set_shared_data(self, key: SharedStateKey, value: Any) -> None:
        """Store shared state under a key object."""
        self._shared_data[key] = value

    def remove_shared_data(self, key: SharedStateKey) -> None:
        """Remove shared state for a key, if present."""
        self._shared_data.pop(key, None)

    def __str__(self):
        return f"EffectState(step_indices={self._step_indices}, step_data={self._step_data})"


class EffectTimer:
    """Tracks frame timing for effect steps.

    ``elapsed`` is the last frame delta, ``total`` is cumulative elapsed time,
    and ``progress`` is normalized to ``[0.0, 1.0]`` when a finite duration is
    set. When ``duration`` is ``None``, ``progress`` stays ``0.0`` and
    ``update`` always returns ``False``.
    """

    __slots__ = ("duration", "elapsed", "progress", "total")

    def __init__(self, duration: float | None = None):
        self.elapsed: float = 0.0
        self.total: float = 0.0
        self.duration: float | None = duration
        self.progress: float = 0.0

    def update(self, elapsed: float) -> bool:
        """Advance timer by one frame delta and return whether duration is complete."""
        self.elapsed = elapsed
        self.total += elapsed
        if self.duration is not None:
            self.progress = min(1.0, self.total / self.duration)

        return self.progress >= 1.0

    def __str__(self) -> str:
        return (
            f"EffectTimer(elapsed={self.elapsed}, total={self.total}, "
            f"duration={self.duration}, progress={self.progress})"
        )


class EffectStep:
    """Base class for steps attached to an ``Effect``.

    A step updates effect state over time and can optionally transform the
    sampling position and output value on each pixel sample.
    """

    def update(self, state: EffectState, timer: EffectTimer) -> bool:
        """Advance step state for one frame.

        Return ``True`` to advance to the next step, ``False`` to stay active.
        """
        raise NotImplementedError("EffectStep subclasses must implement the update method")

    def adjust_position(self, state: EffectState, position: float) -> float:
        """Transform sampling position before the effect shape is evaluated."""
        return position

    def adjust_value(self, state: EffectState, position: float, value: float) -> float:
        """Transform sampled value after shape evaluation and prior step transforms."""
        return value


class Effect:
    """Animates a shape over time using a sequence of steps.

    Each step controls how the effect evolves, allowing behaviors like fading,
    oscillating, or transitioning through distinct phases. The same ``Effect``
    instance can drive multiple independent animations simultaneously by
    keeping all mutable state in an ``EffectState``.

    Update model — call ``update`` once per frame:
    - Only the active step's ``update`` is called.
    - A step returning ``True`` yields control to the next step, wrapping around.
    - Multiple advances can occur in one frame if consecutive steps return ``True``.
    - With no steps, ``update`` is a no-op.

    Sampling model — call ``value`` per pixel:
    - ``adjust_position`` from all steps is applied in order.
    - The transformed position is sampled against the base shape.
    - ``adjust_value`` from all steps is then applied in order.
    - Output is clamped to ``[0.0, 1.0]``.

    Parameters:
    - ``name``: Human-readable identifier for logging and debugging.
    - ``shape_func``: Base shape sampled during ``value``; defaults to a zero shape.
    """

    def __init__(self, name: str, shape_func: EffectShapeFunc | None = None):
        self.name = name
        self._shape: EffectShapeFunc = shape_func if shape_func is not None else Shape.none()
        self._steps: list[EffectStep] = []

    def add_steps(self, steps: Iterable[EffectStep]) -> Effect:
        """Append steps and return ``self`` to support fluent construction."""
        self._steps.extend(steps)
        return self

    def update(self, state: EffectState, timer: EffectTimer):
        """Advance the active step and update step state for the current frame."""
        step_index = state.get_step_index(self)
        next_step_index = run_step_updates(self._steps, step_index, state, timer)
        if next_step_index != step_index:
            state.set_step_index(self, next_step_index)

    def value(self, state: EffectState, position: float) -> float:
        """Sample the effect at ``position`` after all step transforms.

        Order: ``adjust_position`` (all steps) → shape → ``adjust_value`` (all steps).
        Output is clamped to ``[0.0, 1.0]``.
        """
        steps = self._steps
        for step in steps:
            position = step.adjust_position(state, position)

        shape_value = self._shape(position)
        for step in steps:
            shape_value = step.adjust_value(state, position, shape_value)

        return max(0.0, min(1.0, shape_value))

    def __str__(self):
        return f"Effect(name={self.name}) at {hex(id(self))}"
