"""Radio mode: A sends a test packet; a packet received flashes the global strips green.

The idle is white on every strip, so the green flash shows over it.
"""

from __future__ import annotations

from app.simulation import TICK
from packs.scenes.hardware_test.rules.helpers.hw_mode_rule import FLASH_DURATION
from packs.scenes.hardware_test.rules.helpers.mode import HW_TEST_PAYLOAD
from packs.scenes.hardware_test.tests.helpers import (
    GLOBAL_STRIPS,
    GREEN,
    IR,
    RADIO,
    WHITE,
    all_white,
    every_global_strip_lit,
    press,
    send_on_a,
    strips_but,
)


def test_entering_radio_mode_lights_every_strip_white(sim):
    device = sim.add_device("red", scene="hardware_test")

    press(device, "B", RADIO)

    assert all_white(device)


def test_a_sends_the_test_payload_by_radio(sim):
    device = sim.add_device("red", scene="hardware_test")
    press(device, "B", RADIO)
    device.forget()

    device.tap("A")

    assert [s.payload for s in device.radio_sent] == [HW_TEST_PAYLOAD]


def test_a_sends_no_radio_outside_radio_mode(sim):
    device = sim.add_device("red", scene="hardware_test")
    press(device, "B", IR)

    device.tap("A")

    assert device.radio_sent == []


def test_a_logs_that_it_is_sending_a_packet(sim, capsys):
    device = sim.add_device("red", scene="hardware_test")
    press(device, "B", RADIO)
    capsys.readouterr()

    device.tap("A")

    assert "sending radio packet" in capsys.readouterr().out


def test_a_logs_no_packet_sent_outside_radio_mode(sim, capsys):
    device = sim.add_device("red", scene="hardware_test")
    press(device, "B", IR)
    capsys.readouterr()

    device.tap("A")

    assert "sending radio packet" not in capsys.readouterr().out


def test_a_packet_from_another_device_flashes_the_global_strips_green(sim):
    red = sim.add_device("red", scene="hardware_test")
    blue = sim.add_device("blue", scene="hardware_test")
    press(red, "B", RADIO)
    press(blue, "B", RADIO)

    red.tap("A")

    assert every_global_strip_lit(blue, GREEN)


def test_a_received_packet_flashes_only_the_global_strips(sim):
    red = sim.add_device("red", scene="hardware_test")
    blue = sim.add_device("blue", scene="hardware_test")
    press(red, "B", RADIO)
    press(blue, "B", RADIO)

    red.tap("A")

    assert all(blue.strip(scope).all_lit(WHITE) for scope in strips_but(*GLOBAL_STRIPS))


def test_the_flash_holds_for_the_flash_duration(sim):
    red = sim.add_device("red", scene="hardware_test")
    blue = sim.add_device("blue", scene="hardware_test")
    press(red, "B", RADIO)
    press(blue, "B", RADIO)
    send_on_a(sim, red)

    sim.advance(FLASH_DURATION - TICK)

    assert every_global_strip_lit(blue, GREEN)


def test_once_the_flash_duration_has_passed_the_global_strips_return_to_white(sim):
    red = sim.add_device("red", scene="hardware_test")
    blue = sim.add_device("blue", scene="hardware_test")
    press(red, "B", RADIO)
    press(blue, "B", RADIO)
    send_on_a(sim, red)

    sim.advance(FLASH_DURATION + TICK)

    assert all_white(blue)


def test_a_received_packet_logs_its_payload_and_sender(sim, capsys):
    # From outside the Simulation: no device in it sends this payload.
    device = sim.add_device("red", scene="hardware_test")
    press(device, "B", RADIO)
    capsys.readouterr()

    device.receive_radio(b"payload-xyz", sender=7)
    sim.advance(TICK)

    assert "radio received b'payload-xyz' from 7" in capsys.readouterr().out


def test_a_device_does_not_flash_at_its_own_packet(sim):
    device = sim.add_device("red", scene="hardware_test")
    press(device, "B", RADIO)

    device.tap("A")
    sim.advance(TICK)

    assert every_global_strip_lit(device, WHITE)


def test_a_packet_received_outside_radio_mode_does_not_flash(sim):
    # IR mode idles white on every strip too, so a green flash would show.
    red = sim.add_device("red", scene="hardware_test")
    blue = sim.add_device("blue", scene="hardware_test")
    press(red, "B", RADIO)
    press(blue, "B", IR)

    red.tap("A")
    sim.advance(TICK)

    assert all_white(blue)
