"""Tests for ProgressFillEffect's clock: how its progress follows elapsed time.

The pixel mapping is ``ProgressRenderer``'s and is tested there. Progress is
read back from the layer as the lit fraction of a one-pixel bar, which equals
the progress itself.
"""

from __future__ import annotations

import pytest

from effects.layers.progress_layer import ProgressLayer
from packs.scenes.tag.effects.helpers.progress_fill_effect import ProgressFillEffect


def _fill(duration: float) -> tuple[ProgressFillEffect, ProgressLayer]:
    layer = ProgressLayer(0.0)
    return ProgressFillEffect(layer, color=0xFF0000, duration=duration), layer


def _progress(layer: ProgressLayer) -> float:
    return layer.sample(0.0, 1)


def test_progress_is_empty_before_any_update() -> None:
    _, layer = _fill(duration=2.0)

    assert _progress(layer) == 0.0


def test_progress_is_elapsed_over_duration_mid_way() -> None:
    effect, layer = _fill(duration=2.0)

    effect.update(0.5)

    assert _progress(layer) == pytest.approx(0.25)


def test_progress_accumulates_elapsed_across_updates() -> None:
    effect, layer = _fill(duration=2.0)

    effect.update(0.5)
    effect.update(1.0)

    assert _progress(layer) == pytest.approx(0.75)


def test_progress_is_full_at_the_duration() -> None:
    effect, layer = _fill(duration=2.0)

    effect.update(2.0)

    assert _progress(layer) == 1.0


def test_progress_stays_full_after_the_duration() -> None:
    effect, layer = _fill(duration=2.0)

    effect.update(2.0)
    effect.update(5.0)

    assert _progress(layer) == 1.0


def test_zero_duration_is_full_on_the_first_update() -> None:
    effect, layer = _fill(duration=0.0)

    effect.update(0.0)

    assert _progress(layer) == 1.0
