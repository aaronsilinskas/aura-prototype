import random

from effects.layers.layer import Layer
from effects.value import lerp


class FlameLayer(Layer):
    """Pure flame simulation — no rendering, no palette, no EffectStep overhead.

    Owns the heat array and spark set directly. Call ``update(elapsed)`` each
    frame to advance the simulation, then ``sample(position)`` per pixel to
    read interpolated heat at any normalised position in ``[0.0, 1.0]``.

    The algorithm is identical to ``FlameStep``, enabling fair visual comparison
    between the two design approaches.
    """

    __slots__ = [
        "_cool_rate",
        "_flame_buffer",
        "_flame_count",
        "_heat_rate",
        "_spark_buffer",
        "_spark_count",
        "_sparks_to_remove",
        "_spread_offsets",
        "_spread_weights",
    ]

    def __init__(
        self,
        spark_count: int,
        heat_rate: float,
        extra_cool_rate: float,
        resolution: int,
        spread: float,
    ) -> None:
        self._spark_count = spark_count
        self._flame_count = max(resolution, spark_count * 2)
        self._heat_rate = heat_rate
        spread = min(max(spread, 0.0), 1.0)
        half_flame_spread = int(spread * self._flame_count) // 2

        heat_per_spark = heat_rate
        if half_flame_spread > 0:
            heat_per_spark += heat_rate * (half_flame_spread + 2)
        total_spark_heat = heat_per_spark * spark_count
        cooling_buffer_size = self._flame_count - spark_count
        self._cool_rate = total_spark_heat / cooling_buffer_size + extra_cool_rate

        # Pre-compute non-zero spread offsets and their weights once; avoids
        # per-frame division and abs() calls inside the spark update loop.
        if half_flame_spread > 0:
            inv_hfs = 1.0 / half_flame_spread
            offsets = [o for o in range(-half_flame_spread, half_flame_spread + 1) if o != 0]
            self._spread_offsets: list[int] = offsets
            self._spread_weights: list[float] = [
                (1 + half_flame_spread - abs(o)) * inv_hfs for o in offsets
            ]
        else:
            self._spread_offsets = []
            self._spread_weights = []

        self._flame_buffer = [0.0] * self._flame_count
        self._spark_buffer: set[int] = set()
        for _ in range(spark_count):
            self._spark_buffer.add(random.randint(0, self._flame_count - 1))
        self._sparks_to_remove = [0] * spark_count

    def update(self, elapsed: float) -> None:
        """Advance the simulation by ``elapsed`` seconds."""
        flame_buffer = self._flame_buffer
        spark_buffer = self._spark_buffer
        flame_count = self._flame_count
        spread_offsets = self._spread_offsets
        spread_weights = self._spread_weights
        n_spread = len(spread_offsets)

        cool_delta = self._cool_rate * elapsed
        for i in range(flame_count):
            if i not in spark_buffer:
                v = flame_buffer[i] - cool_delta
                flame_buffer[i] = v if v > 0.0 else 0.0

        spark_heat = self._heat_rate * elapsed
        remove_count = 0
        sparks_to_remove = self._sparks_to_remove

        for spark_index in spark_buffer:
            if flame_buffer[spark_index] < 1.0:
                flame_buffer[spark_index] += spark_heat
                for k in range(n_spread):
                    flame_buffer[(spark_index + spread_offsets[k]) % flame_count] += (
                        spark_heat * spread_weights[k]
                    )
            else:
                sparks_to_remove[remove_count] = spark_index
                remove_count += 1

        for i in range(remove_count):
            spark_buffer.discard(sparks_to_remove[i])

        while len(spark_buffer) < self._spark_count:
            spark_buffer.add(random.randint(0, flame_count - 1))

    def sample(self, position: float, pixel_count: int) -> float:
        """Return interpolated heat at ``position`` in ``[0.0, 1.0]``.

        ``pixel_count`` is accepted for interface uniformity but is not used.
        """
        flame_count = self._flame_count
        flame_offset = position * flame_count
        left = int(flame_offset) % flame_count
        right = (left + 1) % flame_count
        value = lerp(self._flame_buffer[left], self._flame_buffer[right], flame_offset % 1.0)
        return value if value <= 1.0 else 1.0
