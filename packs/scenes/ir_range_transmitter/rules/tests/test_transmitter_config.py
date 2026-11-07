"""Tests for ``TransmitterConfig`` — built from the scene's declared Settings,
its derived values, and the ``transmitter_config`` get-or-create accessor."""

from __future__ import annotations

import pytest

from engine.settings import Settings
from engine.state import EffectControls, GameState, SceneControls
from packs.scenes.ir_range_transmitter.rules.helpers.transmitter_config import (
    TransmitterConfig,
    transmitter_config,
)
from packs.tests.settings_helper import declared_scene_defaults, settings_for


def _settings(**values: object) -> Settings:
    return settings_for("ir_range_transmitter", settings=values)


# ---------------------------------------------------------------------------
# from_settings
# ---------------------------------------------------------------------------


def test_each_scene_setting_override_sets_the_config_field_of_the_same_name():
    config = TransmitterConfig.from_settings(_settings(send_rate_hz=10.0, payload_size=8))

    assert config.send_rate_hz == pytest.approx(10.0)
    assert config.payload_size == 8


def test_with_no_overrides_each_field_holds_its_declared_default():
    defaults = declared_scene_defaults("ir_range_transmitter")

    config = TransmitterConfig.from_settings(_settings())

    assert {name: getattr(config, name) for name in defaults} == defaults


# ---------------------------------------------------------------------------
# Derived values
# ---------------------------------------------------------------------------


def test_send_period_seconds_is_the_reciprocal_of_send_rate():
    config = TransmitterConfig(send_rate_hz=10.0, payload_size=4)

    assert config.send_period_seconds == pytest.approx(0.1)


def test_payload_padding_carries_a_fixed_non_zero_marker_in_every_padding_byte():
    config = TransmitterConfig(send_rate_hz=5.0, payload_size=4)

    assert config.payload_padding == bytes([0xA1, 0xA2, 0xA3])


# ---------------------------------------------------------------------------
# transmitter_config — get-or-create accessor
# ---------------------------------------------------------------------------


def test_transmitter_config_builds_from_the_state_settings():
    state = GameState(EffectControls(), SceneControls(), settings=_settings(payload_size=8))

    assert transmitter_config(state).payload_size == 8


def test_transmitter_config_caches_the_same_instance_across_calls():
    state = GameState(EffectControls(), SceneControls(), settings=_settings())

    assert transmitter_config(state) is transmitter_config(state)
