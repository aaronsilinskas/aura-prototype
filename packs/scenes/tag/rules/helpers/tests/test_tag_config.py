"""Tests for ``TagConfig`` — built from the scene's declared Settings, its
derived values, and the ``tag_config`` get-or-create accessor."""

from __future__ import annotations

import pytest

from engine.settings import Settings
from engine.state import EffectControls, GameState, SceneControls
from packs.scenes.tag.rules.helpers.tag_config import (
    TagConfig,
    tag_config,
)
from packs.tests.settings_helper import declared_scene_defaults, settings_for


def _settings(**values: object) -> Settings:
    return settings_for("tag", settings=values)


# ---------------------------------------------------------------------------
# Construction from Settings
# ---------------------------------------------------------------------------


def test_each_scene_setting_override_sets_the_config_field_of_the_same_name():
    config = TagConfig(
        _settings(
            starting_hitpoints=20,
            expected_team=2,
            expected_player=3,
            warning_pulse_count=4,
            warning_pulse_duration=1.0,
            max_ammo=5,
            shot_cooldown=0.5,
            reload_duration=2.5,
        )
    )

    assert config.starting_hitpoints == 20
    assert config.expected_team == 2
    assert config.expected_player == 3
    assert config.warning_pulse_count == 4
    assert config.warning_pulse_duration == pytest.approx(1.0)
    assert config.max_ammo == 5
    assert config.shot_cooldown == pytest.approx(0.5)
    assert config.reload_duration == pytest.approx(2.5)


def test_with_no_overrides_each_field_holds_its_declared_default():
    defaults = declared_scene_defaults("tag")

    config = TagConfig(_settings())

    assert {name: getattr(config, name) for name in defaults} == defaults


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
