import math

try:
    from collections.abc import Callable
    from typing import TypeAlias
except ImportError:
    pass

from effects.value import GAMMA_FACTOR, DynamicValue, ValueGenerator

EffectShapeFunc: TypeAlias = "Callable[[float], float]"


class Shape:
    """Defines the visual form of an effect — the brightness distribution across a strip.

    Choosing a shape determines what an effect looks like: a full gradient, a
    centered glow, a pulse, a checkerboard, and so on. Shapes are combined with
    steps to build complete effects.

    Contracts:
    - Each method returns an ``EffectShapeFunc``: ``(float) -> float``.
    - Input position is wrapped with modulo into ``[0.0, 1.0]`` before sampling
      unless noted otherwise.
    - Output is a brightness value in ``[0.0, 1.0]``.
    """

    @staticmethod
    def none() -> EffectShapeFunc:
        """Return a shape that always produces ``0.0``."""

        def shape(_: float) -> float:
            return 0.0

        return shape

    @staticmethod
    def gradient() -> EffectShapeFunc:
        """Return a gamma-corrected ramp from ``0.0`` at position ``0.0`` to ``1.0`` at ``1.0``."""
        gamma = GAMMA_FACTOR

        def shape(position: float) -> float:
            return pow(position % 1.0, gamma)

        return shape

    @staticmethod
    def centered_gradient() -> EffectShapeFunc:
        """Return a gamma-corrected ramp that peaks at ``1.0`` in the center
        and falls to ``0.0`` at both edges."""
        gamma = GAMMA_FACTOR

        def shape(position: float) -> float:
            pos = position % 1.0
            if pos < 0.5:
                return pow(pos * 2.0, gamma)

            return pow((1.0 - pos) * 2.0, gamma)

        return shape

    @staticmethod
    def padded(padding: float, shape_func: EffectShapeFunc) -> EffectShapeFunc:
        """Wrap ``shape_func`` with symmetric dead zones on each side.

        ``padding`` is a fraction of the total span clamped to ``[0.0, 0.5]``.
        Positions within the padding regions return ``0.0``; positions inside
        are remapped to ``[0.0, 1.0]`` before being passed to ``shape_func``.
        """
        clamped_padding = max(0.0, min(0.5, padding))
        span = 1.0 - 2.0 * clamped_padding
        if span <= 0.0:
            return Shape.none()

        lower_bound = clamped_padding
        upper_bound = 1.0 - clamped_padding
        inv_span = 1.0 / span

        def shape(position: float) -> float:
            pos = position % 1.0
            if pos < lower_bound:
                return 0.0
            if pos > upper_bound:
                return 0.0

            return shape_func((pos - lower_bound) * inv_span)

        return shape

    @staticmethod
    def reverse(shape_func: EffectShapeFunc) -> EffectShapeFunc:
        """Return ``shape_func`` sampled in reverse, so position ``0.0`` maps
        to ``1.0`` and vice versa."""

        def shape(position: float) -> float:
            return shape_func(1.0 - (position % 1.0))

        return shape

    @staticmethod
    def sine(frequency: DynamicValue) -> EffectShapeFunc:
        """Return a sine wave oscillating between ``0.0`` and ``1.0`` at the given frequency."""
        frequency_value = ValueGenerator.resolve(frequency)
        tau = 2.0 * math.pi

        def shape(position: float) -> float:
            return math.sin(frequency_value * position * tau) / 2.0 + 0.5

        return shape

    @staticmethod
    def checkers(value: float, count: int, width: float) -> EffectShapeFunc:
        """Return a repeating checker pattern of ``count`` segments across ``[0.0, 1.0]``.

        Each checker has a flat region at ``value`` followed by a short fade to
        ``0.0`` controlled by ``width`` (fraction of segment, clamped to
        ``[0.0, 1.0]``).
        """
        clamped_width = max(0.0, min(1.0, width))
        if count <= 0 or clamped_width <= 0.0:
            return Shape.none()

        span = 1.0 / count

        def shape(position: float) -> float:
            pos = position % 1.0
            mod_pos = pos % span

            if mod_pos < clamped_width:
                return value
            mod_pos -= clamped_width
            if mod_pos < clamped_width:
                return value - (value * mod_pos / clamped_width)

            return 0.0

        return shape
