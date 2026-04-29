import random

from effects.effect import EffectState, EffectStep, EffectTimer
from effects.value import DynamicValue, lerp
from effects.value import ValueGenerator as VG


class FlameStep(EffectStep):
    """Produces a flickering heat animation that resembles a gas flame or heat shimmer.

    Random spark points ignite and spread heat to neighboring cells based on
    ``spread``; all cells cool each frame. Output is additively blended with
    the incoming effect value.
    """

    def __init__(
        self,
        spark_count: DynamicValue,
        heat_rate: DynamicValue,
        extra_cool_rate: DynamicValue,
        resolution: int,
        spread: float = 0.1,
    ):
        self.spark_count = int(VG.resolve(spark_count))
        self.flame_count = max(resolution, self.spark_count * 2)
        self.heat_rate = VG.resolve(heat_rate)
        self.extra_cool_rate = VG.resolve(extra_cool_rate)
        self.spread = min(max(spread, 0.0), 1.0)
        self.half_flame_spread = int(self.spread * self.flame_count) // 2

        # calculate minimum cool rate to ensure flames will cool down enough between sparks
        heat_per_spark = self.heat_rate
        if self.half_flame_spread > 0:
            heat_per_spark += self.heat_rate * (self.half_flame_spread + 2)
        total_spark_heat = heat_per_spark * self.spark_count
        cooling_buffer_size = self.flame_count - self.spark_count
        min_cool_rate = total_spark_heat / cooling_buffer_size
        self.cool_rate = min_cool_rate + self.extra_cool_rate
        self._spread_range = range(-self.half_flame_spread, self.half_flame_spread + 1)

    class _Data:
        __slots__ = ("flame_buffer", "remove_count", "spark_buffer", "sparks_to_remove")

        def __init__(self, spark_count: int, flame_count: int):
            self.spark_buffer: set[int] = set()
            for _ in range(spark_count):
                self.spark_buffer.add(random.randint(0, flame_count - 1))
            self.flame_buffer = [0.0] * flame_count
            self.sparks_to_remove = [0] * spark_count
            self.remove_count = 0

    def update(self, state: EffectState, timer: EffectTimer) -> bool:
        data = state.get_step_data(self, FlameStep._Data)
        if data is None:
            data = self._Data(self.spark_count, self.flame_count)
            state.set_step_data(self, data)

        spark_buffer = data.spark_buffer
        flame_buffer = data.flame_buffer
        flame_count = self.flame_count

        # Cool down existing flames
        cool_delta = self.cool_rate * timer.elapsed
        for i in range(flame_count):
            if i not in spark_buffer:
                flame = flame_buffer[i]
                flame -= cool_delta
                if flame < 0.0:
                    flame = 0.0
                flame_buffer[i] = flame

        # Heat up around new sparks
        half_flame_spread = self.half_flame_spread
        spark_heat = self.heat_rate * timer.elapsed
        remove_count = 0
        sparks_to_remove = data.sparks_to_remove

        for spark_index in spark_buffer:
            if flame_buffer[spark_index] < 1.0:
                # spark not at max heat yet, so heat it up and neighbors
                for offset in self._spread_range:
                    if offset == 0:
                        flame_buffer[spark_index] += spark_heat
                    else:
                        flame_buffer[(spark_index + offset) % flame_count] += (
                            spark_heat * (1 + half_flame_spread - abs(offset)) / half_flame_spread
                        )
            else:
                # defer removal so we don't mutate the set during iteration
                sparks_to_remove[remove_count] = spark_index
                remove_count += 1

        for i in range(remove_count):
            spark_buffer.discard(sparks_to_remove[i])

        # replenish sparks if needed
        while len(spark_buffer) < self.spark_count:
            spark_buffer.add(random.randint(0, flame_count - 1))

        return True

    def adjust_value(self, state: EffectState, position: float, value: float) -> float:
        data = state.get_step_data(self, FlameStep._Data)
        if data is not None:
            flame_offset = position * self.flame_count
            left_index = int(flame_offset) % self.flame_count
            right_index = (left_index + 1) % self.flame_count
            index_weight = flame_offset % 1.0
            blended_flame_value = lerp(
                data.flame_buffer[left_index],
                data.flame_buffer[right_index],
                index_weight,
            )
            value = min(1.0, value + blended_flame_value)

        return value


def flame(
    spark_count: DynamicValue,
    heat_rate: DynamicValue = 0.7,
    extra_cool_rate: DynamicValue = 0.0,
    resolution: int = 16,
    spread: float = 0.1,
) -> EffectStep:
    """Return a step that overlays a flame simulation onto the effect."""
    return FlameStep(spark_count, heat_rate, extra_cool_rate, resolution, spread)
