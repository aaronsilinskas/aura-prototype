from effects.layers.flame_layer import FlameLayer

# ---------------------------------------------------------------------------
# FlameLayer — sample range
# ---------------------------------------------------------------------------


def test_flame_layer_sample_returns_value_in_unit_range_before_update() -> None:
    layer = FlameLayer(spark_count=3, heat_rate=2.0, extra_cool_rate=0.5, resolution=20, spread=0.3)

    for i in range(10):
        v = layer.sample(i / 10, 30)
        assert 0.0 <= v <= 1.0, f"sample({i / 10}) = {v} out of range"


def test_flame_layer_sample_returns_value_in_unit_range_after_updates() -> None:
    layer = FlameLayer(spark_count=3, heat_rate=2.0, extra_cool_rate=0.5, resolution=20, spread=0.3)
    for _ in range(30):
        layer.update(0.016)

    for i in range(10):
        v = layer.sample(i / 10, 30)
        assert 0.0 <= v <= 1.0, f"sample({i / 10}) = {v} out of range"


# ---------------------------------------------------------------------------
# FlameLayer — simulation produces variation
# ---------------------------------------------------------------------------


def test_flame_layer_samples_vary_across_positions_after_update() -> None:
    layer = FlameLayer(spark_count=3, heat_rate=2.0, extra_cool_rate=0.1, resolution=20, spread=0.3)
    for _ in range(60):
        layer.update(0.016)

    samples = [layer.sample(i / 20, 30) for i in range(20)]

    assert max(samples) > min(samples), "all samples identical — flame simulation not running"


def test_flame_layer_produces_nonzero_heat_after_sustained_updates() -> None:
    layer = FlameLayer(spark_count=3, heat_rate=5.0, extra_cool_rate=0.1, resolution=20, spread=0.3)
    for _ in range(60):
        layer.update(0.016)

    samples = [layer.sample(i / 20, 30) for i in range(20)]

    assert any(v > 0.0 for v in samples), "no heat after sustained updates"


# ---------------------------------------------------------------------------
# FlameLayer — spread=0 still works
# ---------------------------------------------------------------------------


def test_flame_layer_with_zero_spread_samples_in_unit_range() -> None:
    layer = FlameLayer(spark_count=2, heat_rate=2.0, extra_cool_rate=0.5, resolution=10, spread=0.0)
    for _ in range(10):
        layer.update(0.016)

    for i in range(10):
        v = layer.sample(i / 10, 10)
        assert 0.0 <= v <= 1.0
