class Layer:
    """Base interface for simulation layers.

    All concrete subclasses must implement ``update`` and ``sample``.

    This class uses ``raise NotImplementedError`` rather than ``abc.ABC`` /
    ``@abstractmethod`` for CircuitPython compatibility.

    ``__slots__ = []`` allows subclasses to define their own ``__slots__``
    without accidentally adding a ``__dict__``.
    """

    __slots__ = []

    def update(self, elapsed: float) -> None:
        """Advance internal simulation state by ``elapsed`` seconds."""
        raise NotImplementedError

    def sample(self, position: float, pixel_count: int) -> float:
        """Return the intensity at normalised position ``[0.0, 1.0)`` in ``[0.0, 1.0]``.

        ``pixel_count`` is the number of pixels in the output.  Layers
        that need per-pixel falloff (e.g. ``SparkleLayer``) use it; others
        accept the argument and ignore it.
        """
        raise NotImplementedError
