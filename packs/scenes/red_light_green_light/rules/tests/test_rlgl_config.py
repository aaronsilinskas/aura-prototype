"""Tests for ``RlglConfig`` -- warning sting options, the cross-Setting check
(gravity tracking slower than motion smoothing), and the ``rlgl_config``
get-or-create accessor.

``packs/tests/test_scene_configs.py`` checks that each Setting lands in its field."""

from __future__ import annotations

import pytest

from engine.settings import Settings
from engine.state import EffectControls, GameState, SceneControls
from packs.scenes.red_light_green_light.rules.helpers.rlgl_config import (
    RlglConfig,
    rlgl_config,
)
from packs.tests.settings_helper import settings_for


def _settings(**values: object) -> Settings:
    return settings_for("red_light_green_light", settings=values)


# ---------------------------------------------------------------------------
# Warning sting options builder
# ---------------------------------------------------------------------------


def test_warning_sting_opts_uses_breathe_cycle_ratios_of_pulse_duration():
    config = RlglConfig(_settings(warning_pulse_max=1.0, warning_pulse_min=0.4, max_level=10))

    opts = config.warning_sting_opts(1)

    assert opts["start_color"] == 0x000000
    assert opts["end_color"] == 0xFFFF00
    assert opts["brighten_duration"] == pytest.approx(0.3)
    assert opts["on_duration"] == pytest.approx(0.4)
    assert opts["darken_duration"] == pytest.approx(0.3)
    assert opts["off_duration"] == 0.0


def test_warning_sting_opts_scales_sub_durations_with_level():
    config = RlglConfig(_settings(warning_pulse_max=1.0, warning_pulse_min=0.4, max_level=10))

    opts = config.warning_sting_opts(10)

    pulse = 0.4
    assert opts["brighten_duration"] == pytest.approx(pulse * 0.3)
    assert opts["on_duration"] == pytest.approx(pulse * 0.4)
    assert opts["darken_duration"] == pytest.approx(pulse * 0.3)


# ---------------------------------------------------------------------------
# Cross-Setting check: gravity tracking slower than motion smoothing
# ---------------------------------------------------------------------------


def test_the_declared_gravity_tracking_is_slower_than_motion_smoothing():
    """Gravity must track slower than the motion signal, or real motion is
    absorbed into the gravity estimate before it ever registers."""
    config = RlglConfig(_settings())

    assert config.gravity_beta < config.motion_smoothing


@pytest.mark.parametrize("gravity_beta", [0.3, 0.4])
def test_rejects_gravity_beta_not_below_motion_smoothing(gravity_beta):
    settings = _settings(motion_smoothing=0.3, gravity_beta=gravity_beta)

    expected = rf"gravity_beta \({gravity_beta}\) must be below motion_smoothing \(0\.3\)"
    with pytest.raises(ValueError, match=expected):
        RlglConfig(settings)


# ---------------------------------------------------------------------------
# rlgl_config — get-or-create accessor
# ---------------------------------------------------------------------------


def test_rlgl_config_builds_from_the_state_settings():
    state = GameState(EffectControls(), SceneControls(), settings=_settings(red_duration_max=9.0))

    assert rlgl_config(state).red_duration_max == pytest.approx(9.0)


def test_rlgl_config_caches_the_same_instance_across_calls():
    state = GameState(EffectControls(), SceneControls(), settings=_settings())

    assert rlgl_config(state) is rlgl_config(state)
