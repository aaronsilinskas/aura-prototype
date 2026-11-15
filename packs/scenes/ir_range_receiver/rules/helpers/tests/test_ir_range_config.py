"""Tests for the ``ir_range_config`` get-or-create accessor.

``packs/tests/test_scene_configs.py`` checks that each Setting lands in its field."""

from __future__ import annotations

import pytest

from engine.settings import Settings
from engine.state import EffectControls, GameState, SceneControls
from packs.scenes.ir_range_receiver.rules.helpers.ir_range_config import (
    ir_range_config,
)
from packs.tests.settings_helper import settings_for


def _settings(**values: object) -> Settings:
    return settings_for("ir_range_receiver", settings=values)


# ---------------------------------------------------------------------------
# ir_range_config — get-or-create accessor
# ---------------------------------------------------------------------------


def test_ir_range_config_builds_from_the_state_settings():
    state = GameState(EffectControls(), SceneControls(), settings=_settings(window_seconds=3.0))

    assert ir_range_config(state).window_seconds == pytest.approx(3.0)


def test_ir_range_config_caches_the_same_instance_across_calls():
    state = GameState(EffectControls(), SceneControls(), settings=_settings())

    assert ir_range_config(state) is ir_range_config(state)
