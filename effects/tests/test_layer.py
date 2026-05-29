import pytest

from effects.layer import Layer

# ---------------------------------------------------------------------------
# Layer — abstract interface
# ---------------------------------------------------------------------------


def test_layer_update_raises_not_implemented() -> None:
    layer = Layer()

    with pytest.raises(NotImplementedError):
        layer.update(0.016)


def test_layer_sample_raises_not_implemented() -> None:
    layer = Layer()

    with pytest.raises(NotImplementedError):
        layer.sample(0.5, 10)
