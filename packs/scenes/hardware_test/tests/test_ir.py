"""IR mode: A sends a test shot and plays the cue; a received shot flashes directional green.

The idle is white on every strip, so the green flash shows over it.
"""

from __future__ import annotations

from app.simulation import TICK
from effects.effect import HapticPattern
from engine.network import LINE
from engine.state import Scope
from packs.scenes.hardware_test.rules.helpers.hw_mode_rule import FLASH_DURATION
from packs.scenes.hardware_test.rules.helpers.mode import HW_TEST_PAYLOAD
from packs.scenes.hardware_test.tests.helpers import EVERY_STRIP, GREEN, IR, WHITE, enter_mode


def test_entering_ir_mode_lights_every_strip_white(sim):
    device = sim.add_device("red", scene="hardware_test")

    enter_mode(device, IR)

    assert all(device.strip(scope).all_lit(WHITE) for scope in EVERY_STRIP)


def test_a_sends_the_test_payload_on_the_line_emitter(sim):
    device = sim.add_device("red", scene="hardware_test")
    enter_mode(device, IR)
    device.forget()

    device.tap("A")

    assert [(s.emitter, s.payload) for s in device.ir_sent] == [(LINE, HW_TEST_PAYLOAD)]


def test_a_plays_the_test_sound_with_a_strong_click(sim):
    device = sim.add_device("red", scene="hardware_test")
    enter_mode(device, IR)

    device.tap("A")

    assert device.has_played("scene.sfx_test_start")
    assert [b.pattern for b in device.buzzed] == [(HapticPattern.STRONG_CLICK,)]


def test_a_shot_received_flashes_the_directional_strip_green(sim):
    red = sim.add_device("red", scene="hardware_test")
    blue = sim.add_device("blue", scene="hardware_test")
    enter_mode(red, IR)
    enter_mode(blue, IR)
    red.aim(LINE, at=blue)

    red.tap("A")

    assert blue.strip(Scope.DIRECTIONAL).all_lit(GREEN)


def test_a_received_shot_flashes_only_the_directional_strip(sim):
    device = sim.add_device("red", scene="hardware_test")
    enter_mode(device, IR)

    device.receive_ir(HW_TEST_PAYLOAD)
    sim.advance(TICK)

    others = [scope for scope in EVERY_STRIP if scope is not Scope.DIRECTIONAL]
    assert all(device.strip(scope).all_lit(WHITE) for scope in others)


def test_the_flash_holds_for_the_flash_duration(sim):
    device = sim.add_device("red", scene="hardware_test")
    enter_mode(device, IR)
    device.receive_ir(HW_TEST_PAYLOAD)
    sim.advance(TICK)

    sim.advance(FLASH_DURATION - TICK)

    assert device.strip(Scope.DIRECTIONAL).all_lit(GREEN)


def test_once_the_flash_duration_has_passed_the_directional_strip_returns_to_white(sim):
    device = sim.add_device("red", scene="hardware_test")
    enter_mode(device, IR)
    device.receive_ir(HW_TEST_PAYLOAD)
    sim.advance(TICK)

    sim.advance(FLASH_DURATION + TICK)

    assert device.strip(Scope.DIRECTIONAL).all_lit(WHITE)


def test_a_device_does_not_flash_at_its_own_shot(sim):
    device = sim.add_device("red", scene="hardware_test")
    enter_mode(device, IR)

    device.tap("A")

    assert device.strip(Scope.DIRECTIONAL).all_lit(WHITE)


def test_a_shot_received_outside_ir_mode_does_not_flash(sim):
    # RGB shows fire on the directional strip, which is never green.
    device = sim.add_device("red", scene="hardware_test")

    device.receive_ir(HW_TEST_PAYLOAD)
    sim.advance(TICK)

    assert not device.strip(Scope.DIRECTIONAL).all_lit(GREEN)
