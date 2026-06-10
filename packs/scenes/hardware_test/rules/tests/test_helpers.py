"""Tests for the hw_test rules/helpers subpackage."""

from __future__ import annotations

import pytest

from engine.state import GameState, SceneControls
from engine.tests.helpers import SpyEffectControls
from packs.scenes.hardware_test.rules.helpers.mode import current_mode


@pytest.fixture()
def state() -> GameState:
    return GameState(SpyEffectControls(), SceneControls())


def test_current_mode_returns_seeded_hw_mode(state):
    state.set("hw_mode", 3)

    assert current_mode(state) == 3


def test_current_mode_defaults_to_zero_when_hw_mode_absent(state):
    assert current_mode(state) == 0
