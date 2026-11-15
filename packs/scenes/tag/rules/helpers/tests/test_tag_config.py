"""Tests for ``TagConfig``'s derived values and the ``tag_config`` get-or-create
accessor.

``packs/tests/test_scene_configs.py`` checks that each Setting lands in its field."""

from __future__ import annotations

import pytest

from engine.settings import Settings
from engine.state import EffectControls, GameState, SceneControls
from packs.scenes.tag.rules.helpers.tag_config import (
    TagConfig,
    tag_config,
)
from packs.tests.settings_helper import settings_for


def _settings(**values: object) -> Settings:
    return settings_for("tag", settings=values)


# ---------------------------------------------------------------------------
# warning_duration
# ---------------------------------------------------------------------------


def test_warning_duration_is_count_times_pulse_duration():
    config = TagConfig(_settings(warning_pulse_count=5, warning_pulse_duration=0.6))

    assert config.warning_duration() == pytest.approx(3.0)


# ---------------------------------------------------------------------------
# tag_config — get-or-create accessor
# ---------------------------------------------------------------------------


def test_tag_config_builds_from_the_state_settings():
    state = GameState(EffectControls(), SceneControls(), settings=_settings(starting_hitpoints=20))

    assert tag_config(state).starting_hitpoints == 20


def test_tag_config_caches_the_same_instance_across_calls():
    state = GameState(EffectControls(), SceneControls(), settings=_settings())

    assert tag_config(state) is tag_config(state)
