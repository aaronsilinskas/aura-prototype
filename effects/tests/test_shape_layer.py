from effects.shape_layer import ShapeLayer

# ---------------------------------------------------------------------------
# ShapeLayer — delegates to shape function
# ---------------------------------------------------------------------------


def test_shape_layer_sample_returns_shape_function_value() -> None:
    # lambda returns position directly — no gamma correction
    layer = ShapeLayer(lambda pos: pos)

    assert abs(layer.sample(0.0, 10) - 0.0) < 1e-9
    assert abs(layer.sample(0.5, 10) - 0.5) < 1e-9
    assert abs(layer.sample(1.0, 10) - 1.0) < 1e-9


def test_shape_layer_sample_clamps_values_above_one_to_one() -> None:
    # shape function that returns 2.0 — should be clamped
    layer = ShapeLayer(lambda pos: 2.0)

    assert layer.sample(0.5, 10) == 1.0


def test_shape_layer_sample_does_not_clamp_values_at_or_below_one() -> None:
    layer = ShapeLayer(lambda pos: 0.8)

    assert layer.sample(0.5, 10) == 0.8


def test_shape_layer_sample_passes_position_to_shape_function() -> None:
    recorded: list[float] = []

    def capture(pos: float) -> float:
        recorded.append(pos)
        return 0.0

    layer = ShapeLayer(capture)
    layer.sample(0.75, 10)

    assert recorded == [0.75]


# ---------------------------------------------------------------------------
# ShapeLayer — update is a no-op
# ---------------------------------------------------------------------------


def test_shape_layer_update_does_not_change_sample_result() -> None:
    layer = ShapeLayer(lambda pos: pos)
    v_before = layer.sample(0.5, 10)

    layer.update(1.0)

    v_after = layer.sample(0.5, 10)
    assert v_before == v_after
