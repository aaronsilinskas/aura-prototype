"""Tests for ``IrRangeConfig`` -- ``from_state`` defaults/overrides and the
``ir_range_config`` get-or-create accessor. Mirrors ``test_rlgl_config.py``."""

from __future__ import annotations

import pytest

from engine.engine import GameEngine
from engine.state import SceneControls
from engine.tests.helpers import SpyEffectControls
from packs.scenes.ir_range_receiver.rules.helpers.ir_range_config import (
    IrRangeConfig,
    ir_range_config,
)


class _StubTimer:
    def __init__(self) -> None:
        self.elapsed: float = 0.0
        self.total: float = 0.0

    def update(self) -> None:
        pass


def _make_state(initial_data: dict | None = None):
    spy = SpyEffectControls()
    timer = _StubTimer()
    engine = GameEngine(spy, timer=timer)  # pyright: ignore[reportArgumentType]
    return engine.create_state(SceneControls(), initial_data=initial_data or {})


# ---------------------------------------------------------------------------
# from_state -- defaults and overrides
# ---------------------------------------------------------------------------


def test_from_state_applies_defaults_when_unseeded():
    state = _make_state()

    config = IrRangeConfig.from_state(state)

    assert config.window_seconds == pytest.approx(1.0)
    assert config.silence_timeout == pytest.approx(0.5)
    assert config.green_threshold == pytest.approx(1.0)


def test_from_state_reads_seeded_overrides():
    state = _make_state(
        initial_data={
            "ir_range_window_seconds": 2.0,
            "ir_range_silence_timeout": 0.75,
            "ir_range_green_threshold": 0.95,
        }
    )

    config = IrRangeConfig.from_state(state)

    assert config.window_seconds == pytest.approx(2.0)
    assert config.silence_timeout == pytest.approx(0.75)
    assert config.green_threshold == pytest.approx(0.95)


# ---------------------------------------------------------------------------
# ir_range_config -- get-or-create accessor
# ---------------------------------------------------------------------------


def test_ir_range_config_reflects_seeded_overrides_on_first_build():
    state = _make_state(initial_data={"ir_range_window_seconds": 3.0})

    assert ir_range_config(state).window_seconds == pytest.approx(3.0)


def test_ir_range_config_caches_the_same_instance_across_calls():
    state = _make_state(initial_data={"ir_range_silence_timeout": 0.75})

    first = ir_range_config(state)
    second = ir_range_config(state)

    assert first is second


def test_ir_range_config_does_not_reflect_state_changes_after_first_build():
    """The config is built once and cached -- later state mutations are not re-read."""
    state = _make_state(initial_data={"ir_range_window_seconds": 3.0})

    config = ir_range_config(state)
    assert config.window_seconds == pytest.approx(3.0)

    state.set("ir_range_window_seconds", 1.0)

    assert ir_range_config(state).window_seconds == pytest.approx(3.0)
