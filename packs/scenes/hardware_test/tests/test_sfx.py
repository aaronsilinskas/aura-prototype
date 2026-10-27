"""SFX mode: personal shows cyan, and A plays the test sound with a strong click.

The test cue is the scene-local ``sfx_test`` effect, tested here through its scene.
"""

from __future__ import annotations

import pytest

from effects.effect import HapticPattern
from engine.state import Scope
from packs.scenes.hardware_test.tests.helpers import (
    ACCELEROMETER,
    CYAN,
    RADIO,
    RGB,
    SFX,
    press,
    strips_but,
)

TEST_SOUND = "scene.sfx_test_start"


def test_entering_sfx_mode_lights_the_personal_strip_cyan(sim):
    device = sim.add_device("red", scene="hardware_test")

    press(device, "B", SFX)

    assert device.strip(Scope.PERSONAL).all_lit(CYAN)


def test_entering_sfx_mode_leaves_every_other_strip_dark(sim):
    # Radio mode, just before, lights every strip white.
    device = sim.add_device("red", scene="hardware_test")

    press(device, "B", SFX)

    assert all(device.strip(scope).dark for scope in strips_but(Scope.PERSONAL))


def test_a_plays_the_test_sound(sim):
    device = sim.add_device("red", scene="hardware_test")
    press(device, "B", SFX)

    device.tap("A")

    assert device.has_played(TEST_SOUND)


def test_a_buzzes_a_strong_click(sim):
    device = sim.add_device("red", scene="hardware_test")
    press(device, "B", SFX)

    device.tap("A")

    assert [b.pattern for b in device.buzzed] == [(HapticPattern.STRONG_CLICK,)]


def test_the_test_sound_plays_once_through_without_looping(sim):
    device = sim.add_device("red", scene="hardware_test")
    press(device, "B", SFX)
    device.tap("A")

    sim.advance(device.clip_length(TEST_SOUND))

    assert not device.is_playing(TEST_SOUND)


@pytest.mark.parametrize("mode", [RGB, ACCELEROMETER, RADIO], ids=["rgb", "accelerometer", "radio"])
def test_a_outside_sfx_and_ir_mode_is_silent(sim, mode):
    device = sim.add_device("red", scene="hardware_test")
    press(device, "B", mode)

    device.tap("A")

    assert device.played == []
    assert device.buzzed == []


def test_b_in_sfx_mode_is_silent(sim):
    device = sim.add_device("red", scene="hardware_test")
    press(device, "B", SFX)

    device.tap("B")

    assert device.played == []
    assert device.buzzed == []
