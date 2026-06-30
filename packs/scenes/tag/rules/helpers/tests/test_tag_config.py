"""Tests for ``TagConfig`` — defaults, ``from_state``, and the ``tag_config``
get-or-create accessor."""

from __future__ import annotations

import pytest

from engine.engine import GameEngine
from engine.state import SceneControls
from engine.tests.helpers import SpyEffectControls
from packs.scenes.tag.rules.helpers.tag_config import (
    TagConfig,
    tag_config,
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
# from_state — defaults and overrides
# ---------------------------------------------------------------------------


def test_from_state_applies_defaults_when_unseeded():
    state = _make_state()

    config = TagConfig.from_state(state)

    assert config.starting_hitpoints == 10
    assert config.deafen_window == pytest.approx(0.2)
    assert config.expected_team == 0
    assert config.expected_player == 1
    assert config.warning_pulse_count == 5
    assert config.warning_pulse_duration == pytest.approx(0.6)
    assert config.max_ammo == 10
    assert config.shot_cooldown == pytest.approx(0.3)
    assert config.reload_duration == pytest.approx(3.0)


def test_from_state_reads_seeded_overrides():
    state = _make_state(
        initial_data={
            "tag_starting_hitpoints": 20,
            "tag_deafen_window": 0.25,
            "tag_expected_team": 2,
            "tag_expected_player": 3,
            "tag_warning_pulse_count": 4,
            "tag_warning_pulse_duration": 1.0,
            "tag_max_ammo": 5,
            "tag_shot_cooldown": 0.5,
            "tag_reload_duration": 2.5,
        }
    )

    config = TagConfig.from_state(state)

    assert config.starting_hitpoints == 20
    assert config.deafen_window == pytest.approx(0.25)
    assert config.expected_team == 2
    assert config.expected_player == 3
    assert config.warning_pulse_count == 4
    assert config.warning_pulse_duration == pytest.approx(1.0)
    assert config.max_ammo == 5
    assert config.shot_cooldown == pytest.approx(0.5)
    assert config.reload_duration == pytest.approx(2.5)


# ---------------------------------------------------------------------------
# warning_duration
# ---------------------------------------------------------------------------


def test_warning_duration_is_count_times_pulse_duration():
    config = TagConfig(
        starting_hitpoints=10,
        deafen_window=0.1,
        expected_team=0,
        expected_player=1,
        warning_pulse_count=5,
        warning_pulse_duration=0.6,
        max_ammo=10,
        shot_cooldown=1.0,
        reload_duration=3.0,
    )

    assert config.warning_duration() == pytest.approx(3.0)


# ---------------------------------------------------------------------------
# tag_config — get-or-create accessor
# ---------------------------------------------------------------------------


def test_tag_config_reflects_seeded_overrides_on_first_build():
    state = _make_state(initial_data={"tag_starting_hitpoints": 20})

    assert tag_config(state).starting_hitpoints == 20


def test_tag_config_caches_the_same_instance_across_calls():
    state = _make_state(initial_data={"tag_starting_hitpoints": 20})

    first = tag_config(state)
    second = tag_config(state)

    assert first is second


def test_tag_config_does_not_reflect_state_changes_after_first_build():
    """The config is built once and cached — later state mutations are not re-read."""
    state = _make_state(initial_data={"tag_starting_hitpoints": 20})

    config = tag_config(state)
    assert config.starting_hitpoints == 20

    state.set("tag_starting_hitpoints", 5)

    assert tag_config(state).starting_hitpoints == 20
