from effects.sparkle_layer import SparkleLayer

# ---------------------------------------------------------------------------
# SparkleLayer — sample range
# ---------------------------------------------------------------------------


def test_sparkle_layer_sample_returns_zero_for_all_slots_before_first_spawn() -> None:
    # spawn_delay_rate=100.0 means slots stay idle far longer than our test runs
    layer = SparkleLayer(
        sparkle_count=3,
        spawn_delay_rate=100.0,
        fade_in_rate=1.0,
        fade_out_rate=1.0,
    )

    for i in range(10):
        assert layer.sample(i / 10, 10) == 0.0


def test_sparkle_layer_produces_nonzero_sample_after_spawn() -> None:
    # spawn_delay_rate=0.05 with 30 × 0.016 s updates → ~0.48 s total
    layer = SparkleLayer(
        sparkle_count=3,
        spawn_delay_rate=0.05,
        fade_in_rate=10.0,  # fast fade-in to guarantee visible intensity
        fade_out_rate=0.1,
    )
    for _ in range(30):
        layer.update(0.016)

    samples = [layer.sample(i / 20, 20) for i in range(20)]
    assert any(v > 0.0 for v in samples), "no non-zero sample after spawn"


# ---------------------------------------------------------------------------
# SparkleLayer — sample uses pixel_count for falloff
# ---------------------------------------------------------------------------


def test_sparkle_layer_sample_peaks_at_sparkle_position() -> None:
    # Use a single sparkle at a known position by driving it to guaranteed spawn
    layer = SparkleLayer(
        sparkle_count=1,
        spawn_delay_rate=0.0,  # zero delay → spawns immediately on first update
        fade_in_rate=100.0,  # instant fade-in
        fade_out_rate=0.01,  # very slow fade-out → stays bright
    )
    # First update: IDLE → FADE_IN (transition via continue, intensity still 0)
    # Second update: FADE_IN → FADE_OUT at full intensity
    layer.update(0.016)
    layer.update(0.016)

    pixel_count = 30
    samples = [layer.sample(i / pixel_count, pixel_count) for i in range(pixel_count)]
    peak = max(samples)
    assert peak > 0.0
    # Falloff — sample far from the sparkle is lower than the peak
    assert min(samples) < peak
