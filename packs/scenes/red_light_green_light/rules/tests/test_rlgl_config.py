"""Tests for ``RlglConfig`` — warning sting options, ``from_state`` defaults,
and the ``rlgl_config`` get-or-create accessor."""

from __future__ import annotations

import pytest

from engine.engine import GameEngine
from engine.state import SceneControls
from engine.tests.helpers import SpyEffectControls
from packs.scenes.red_light_green_light.rules.helpers.rlgl_config import (
    RlglConfig,
    rlgl_config,
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


def _config(**overrides) -> RlglConfig:
    """Build an ``RlglConfig`` directly with sensible defaults, no ``GameState``."""
    defaults = {
        "red_duration_max": 5.0,
        "red_duration_min": 2.0,
        "green_duration_max": 5.0,
        "green_duration_min": 2.0,
        "warning_pulse_max": 1.0,
        "warning_pulse_min": 0.4,
        "game_over_duration": 3.0,
        "green_still_timeout": 0.75,
        "level_up_duration": 1.0,
        "max_level": 10,
        "motion_smoothing": 0.35,
        "gravity_beta": 0.1,
    }
    defaults.update(overrides)
    return RlglConfig(**defaults)


# ---------------------------------------------------------------------------
# Warning sting options builder
# ---------------------------------------------------------------------------


def test_warning_sting_opts_uses_breathe_cycle_ratios_of_pulse_duration():
    config = _config(warning_pulse_max=1.0, warning_pulse_min=0.4, max_level=10)

    opts = config.warning_sting_opts(1)

    assert opts["start_color"] == 0x000000
    assert opts["end_color"] == 0xFFFF00
    assert opts["brighten_duration"] == pytest.approx(0.3)
    assert opts["on_duration"] == pytest.approx(0.4)
    assert opts["darken_duration"] == pytest.approx(0.3)
    assert opts["off_duration"] == 0.0


def test_warning_sting_opts_scales_sub_durations_with_level():
    config = _config(warning_pulse_max=1.0, warning_pulse_min=0.4, max_level=10)

    opts = config.warning_sting_opts(10)

    pulse = 0.4
    assert opts["brighten_duration"] == pytest.approx(pulse * 0.3)
    assert opts["on_duration"] == pytest.approx(pulse * 0.4)
    assert opts["darken_duration"] == pytest.approx(pulse * 0.3)


# ---------------------------------------------------------------------------
# from_state — defaults and overrides
# ---------------------------------------------------------------------------


def test_from_state_applies_defaults_when_unseeded():
    state = _make_state()

    config = RlglConfig.from_state(state)

    assert config.red_duration_max == pytest.approx(5.0)
    assert config.red_duration_min == pytest.approx(2.0)
    assert config.green_duration_max == pytest.approx(5.0)
    assert config.green_duration_min == pytest.approx(2.0)
    assert config.warning_pulse_max == pytest.approx(1.0)
    assert config.warning_pulse_min == pytest.approx(0.4)
    assert config.game_over_duration == pytest.approx(3.0)
    assert config.green_still_timeout == pytest.approx(0.75)
    assert config.level_up_duration == pytest.approx(1.0)
    assert config.max_level == 10


def test_rlgl_config_caches_the_same_instance_across_calls():
    state = _make_state(initial_data={"rlgl_red_duration": 9.0})

    first = rlgl_config(state)
    second = rlgl_config(state)

    assert first is second


def test_rlgl_config_does_not_reflect_state_changes_after_first_build():
    """The config is built once and cached — later state mutations are not re-read."""
    state = _make_state(initial_data={"rlgl_red_duration": 9.0})

    config = rlgl_config(state)
    assert config.red_duration_max == pytest.approx(9.0)

    state.set("rlgl_red_duration", 1.0)

    assert rlgl_config(state).red_duration_max == pytest.approx(9.0)
