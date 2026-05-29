from __future__ import annotations

import random

try:
    from collections.abc import Callable
    from typing import TypeAlias
except ImportError:
    pass  # No typing support on CircuitPython yet

GAMMA_FACTOR = 2.7

DynamicValue: TypeAlias = "float | Callable[[], float]"


def lerp(a: float, b: float, t: float) -> float:
    """Linearly interpolate between ``a`` and ``b`` by factor ``t``."""
    return a + (b - a) * t


class ValueGenerator:
    """Factory for ``DynamicValue`` callables that produce float values on demand.

    A ``DynamicValue`` is either a plain ``float`` or a zero-argument callable
    returning a ``float``. Use ``resolve`` to evaluate either form uniformly.
    """

    @staticmethod
    def resolve(value: DynamicValue) -> float:
        """Return ``value`` directly, or call it if callable."""
        if callable(value):
            return value()
        return value

    @staticmethod
    def random(min_value: float = 0.0, max_value: float = 1.0) -> DynamicValue:
        """Return a callable that produces a random float in ``[min_value, max_value]``."""
        return lambda: random.uniform(min_value, max_value)

    @staticmethod
    def random_choice(choices: list[float]) -> DynamicValue:
        """Return a callable that picks a random entry from ``choices``."""
        return lambda: random.choice(choices)
