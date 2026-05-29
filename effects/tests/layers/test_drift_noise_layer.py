from effects.layers.drift_noise_layer import DriftNoiseLayer

# ---------------------------------------------------------------------------
# DriftNoiseLayer — sample range
# ---------------------------------------------------------------------------


def test_drift_noise_layer_sample_returns_non_negative_value() -> None:
    layer = DriftNoiseLayer(resolution=10, drift_speed=0.1, amplitude=1.0)

    for i in range(10):
        assert layer.sample(i / 10, 10) >= 0.0


def test_drift_noise_layer_sample_does_not_exceed_amplitude() -> None:
    amplitude = 0.7
    layer = DriftNoiseLayer(resolution=10, drift_speed=0.1, amplitude=amplitude)

    for i in range(20):
        v = layer.sample(i / 20, 20)
        assert v <= amplitude + 1e-9, f"sample exceeded amplitude: {v}"


def test_drift_noise_layer_sample_is_zero_when_amplitude_is_zero() -> None:
    layer = DriftNoiseLayer(resolution=10, drift_speed=0.1, amplitude=0.0)

    for i in range(10):
        assert layer.sample(i / 10, 10) == 0.0


# ---------------------------------------------------------------------------
# DriftNoiseLayer — drift over time
# ---------------------------------------------------------------------------


def test_drift_noise_layer_sample_changes_after_update() -> None:
    layer = DriftNoiseLayer(resolution=10, drift_speed=1.0, amplitude=1.0)
    sample_before = layer.sample(0.5, 10)

    layer.update(0.05)  # shifts offset by 0.5 buffer slots — interpolation changes

    sample_after = layer.sample(0.5, 10)
    assert sample_before != sample_after, "sample unchanged after update — drift not working"
