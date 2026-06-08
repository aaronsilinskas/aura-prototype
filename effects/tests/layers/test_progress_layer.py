from effects.layers.progress_layer import ProgressLayer

# ---------------------------------------------------------------------------
# ProgressLayer — full and empty bars
# ---------------------------------------------------------------------------


def test_progress_zero_returns_zero_for_every_pixel() -> None:
    layer = ProgressLayer(0.0)

    for i in range(10):
        assert layer.sample(i / 10, 10) == 0.0


def test_progress_full_returns_one_for_every_pixel() -> None:
    layer = ProgressLayer(1.0)

    for i in range(10):
        assert layer.sample(i / 10, 10) == 1.0


# ---------------------------------------------------------------------------
# ProgressLayer — partial bar on an even pixel count
# ---------------------------------------------------------------------------


def test_progress_half_lights_first_half_only() -> None:
    layer = ProgressLayer(0.5)

    # 10 pixels, progress 0.5 → first 5 fully lit, last 5 dark
    for i in range(5):
        assert layer.sample(i / 10, 10) == 1.0
    for i in range(5, 10):
        assert layer.sample(i / 10, 10) == 0.0


# ---------------------------------------------------------------------------
# ProgressLayer — boundary pixel anti-aliasing
# ---------------------------------------------------------------------------


def test_progress_mid_pixel_boundary_returns_partial_fraction() -> None:
    # 10 pixels, progress 0.55 → 5.5 lit pixels.
    # pixels 0-4 fully lit, pixel 5 half lit, pixels 6-9 dark.
    layer = ProgressLayer(0.55)

    for i in range(5):
        assert layer.sample(i / 10, 10) == 1.0

    boundary = layer.sample(5 / 10, 10)
    assert 0.0 < boundary < 1.0
    assert abs(boundary - 0.5) < 1e-9

    for i in range(6, 10):
        assert layer.sample(i / 10, 10) == 0.0


# ---------------------------------------------------------------------------
# ProgressLayer — clamping
# ---------------------------------------------------------------------------


def test_progress_below_zero_clamped_to_empty() -> None:
    layer = ProgressLayer(-0.5)

    for i in range(10):
        assert layer.sample(i / 10, 10) == 0.0


def test_progress_above_one_clamped_to_full() -> None:
    layer = ProgressLayer(1.5)

    for i in range(10):
        assert layer.sample(i / 10, 10) == 1.0


# ---------------------------------------------------------------------------
# ProgressLayer — update is a no-op
# ---------------------------------------------------------------------------


def test_progress_update_does_not_change_sample_result() -> None:
    layer = ProgressLayer(0.55)
    before = [layer.sample(i / 10, 10) for i in range(10)]

    layer.update(1.0)

    after = [layer.sample(i / 10, 10) for i in range(10)]
    assert before == after
