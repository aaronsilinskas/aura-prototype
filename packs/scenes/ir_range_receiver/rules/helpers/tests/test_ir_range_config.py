"""Tests for ``IrRangeConfig`` -- built from the scene's declared Settings,
and the ``ir_range_config`` get-or-create accessor."""

from __future__ import annotations

import pytest

from engine.settings import Settings
from engine.state import EffectControls, GameState, SceneControls
from packs.scenes.ir_range_receiver.rules.helpers.ir_range_config import (
    IrRangeConfig,
    ir_range_config,
)
from packs.tests.settings_helper import declared_scene_defaults, settings_for


def _settings(**values: object) -> Settings:
    return settings_for("ir_range_receiver", settings=values)


def test_each_scene_setting_override_sets_the_config_field_of_the_same_name():
    settings = _settings(window_seconds=2.0, silence_timeout=0.75, green_threshold=0.95)

    config = IrRangeConfig(settings)

    assert config.window_seconds == pytest.approx(2.0)
    assert config.silence_timeout == pytest.approx(0.75)
    assert config.green_threshold == pytest.approx(0.95)


def test_with_no_overrides_each_field_holds_its_declared_default():
    defaults = declared_scene_defaults("ir_range_receiver")

    config = IrRangeConfig(_settings())

    assert {name: getattr(config, name) for name in defaults} == defaults


def test_ir_range_config_builds_from_the_state_settings():
    state = GameState(EffectControls(), SceneControls(), settings=_settings(window_seconds=3.0))

    assert ir_range_config(state).window_seconds == pytest.approx(3.0)


def test_ir_range_config_caches_the_same_instance_across_calls():
    state = GameState(EffectControls(), SceneControls(), settings=_settings())

    assert ir_range_config(state) is ir_range_config(state)
