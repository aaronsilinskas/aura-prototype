from effects.layers.layer import Layer


class ProgressLayer(Layer):
    """A color-agnostic linear progress bar expressed as per-pixel lit fractions.

    Stateless: ``update`` is a no-op. ``sample(position, pixel_count)`` returns
    the lit fraction of the pixel at ``position`` — ``1.0`` for fully-covered
    pixels, ``0.0`` for uncovered ones, and a partial value for the single
    boundary pixel (the anti-aliased edge of the bar).

    The lit fraction of pixel ``i`` is ``clamp(progress * pixel_count - i,
    0.0, 1.0)``, where ``i = round(position * pixel_count)``. The bar maps onto
    the actual pixel count, independent of ``EffectConfig.resolution``.

    ``progress`` is clamped to ``[0.0, 1.0]`` in the constructor.
    """

    __slots__ = ["_progress"]

    def __init__(self, progress: float) -> None:
        if progress < 0.0:
            progress = 0.0
        elif progress > 1.0:
            progress = 1.0
        self._progress = progress

    def update(self, elapsed: float) -> None:
        """No-op — the progress bar is stateless."""

    def sample(self, position: float, pixel_count: int) -> float:
        """Return the lit fraction at ``position`` in ``[0.0, 1.0]``."""
        i = round(position * pixel_count)
        f = self._progress * pixel_count - i
        if f <= 0.0:
            return 0.0
        if f >= 1.0:
            return 1.0
        return f
