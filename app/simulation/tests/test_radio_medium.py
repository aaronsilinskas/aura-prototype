"""The radio medium: how radio reaches other simulated devices, and when.

Driven through hardware_test's radio mode, where A sends a test packet and a
received packet flashes every global strip green, and its serial line names
the sender's node.
"""

from __future__ import annotations

import re

import pytest

from app.simulation import TICK, SimulatedDevice, Simulation
from engine.state import Scope
from hardware.simulated.device import RadioSent

# These copy hardware_test's test helpers: the harness's tests stand on no scene's tests.
GREEN = 0x00FF00
HW_TEST_PAYLOAD = b"hw_test"
RADIO_MODE = 4
"""Presses of B from switch-on that reach hardware_test's radio mode."""


@pytest.fixture()
def sim() -> Simulation:
    return Simulation()


def add_in_radio_mode(sim: Simulation, *names: str) -> list[SimulatedDevice]:
    devices = [sim.add_device(name, scene="hardware_test") for name in names]
    for device in devices:
        for _ in range(RADIO_MODE):
            device.tap("B")
    return devices


def heard_from(serial: str) -> list[int]:
    """The sender node of each packet the serial output reports, in order."""
    return [int(node) for node in re.findall(r"radio received .* from (\d+)", serial)]


def flashed(device: SimulatedDevice) -> bool:
    return device.strip(Scope.Global.MAIN).all_lit(GREEN)


# ---------------------------------------------------------------------------
# Reach
# ---------------------------------------------------------------------------


def test_a_send_reaches_every_other_device(sim):
    red, blue, green = add_in_radio_mode(sim, "red", "blue", "green")

    red.tap("A")

    assert flashed(blue)
    assert flashed(green)


def test_a_device_never_hears_its_own_send(sim):
    red, _blue = add_in_radio_mode(sim, "red", "blue")

    red.tap("A")

    assert not flashed(red)


@pytest.mark.parametrize("receiver_first", [False, True], ids=["sender-first", "receiver-first"])
def test_a_send_lands_on_the_tick_after_it_was_sent_whatever_the_add_order(sim, receiver_first):
    names = ("blue", "red") if receiver_first else ("red", "blue")
    devices = dict(zip(names, add_in_radio_mode(sim, *names), strict=True))
    red, blue = devices["red"], devices["blue"]

    red.schedule_hold("A")
    sim.run_until(lambda: bool(red.radio_sent))
    flashed_on_the_send_tick = flashed(blue)
    sim.advance(TICK)

    assert not flashed_on_the_send_tick
    assert flashed(blue)


# ---------------------------------------------------------------------------
# Queueing
# ---------------------------------------------------------------------------


def send_together(sim: Simulation, *senders: SimulatedDevice) -> None:
    """Press A on every sender on the same tick, and run until each has sent."""
    for sender in senders:
        sender.schedule_hold("A")
    sim.run_until(lambda: all(s.radio_sent for s in senders))


def heard_by_receiver(sim: Simulation, capsys: pytest.CaptureFixture[str]) -> list[int]:
    """Tick until the air is quiet; return the sender nodes the last-added device heard, in order.

    For two senders and one receiver added after them. Every device ticks in
    add order, so the receiver's line ends each tick's output; each sender
    hears the other's one packet on the first tick, so later lines are the
    receiver's alone.
    """
    capsys.readouterr()
    sim.advance(TICK)
    heard = heard_from(capsys.readouterr().out)[-1:]
    for _ in range(3):
        sim.advance(TICK)
        heard += heard_from(capsys.readouterr().out)
    return heard


@pytest.mark.parametrize("red_first", [True, False], ids=["red-added-first", "green-added-first"])
def test_sends_on_one_tick_reach_a_receiver_one_per_tick_in_sender_add_order(
    sim, capsys, red_first
):
    names = ("red", "green") if red_first else ("green", "red")
    first, second = add_in_radio_mode(sim, *names)
    add_in_radio_mode(sim, "blue")  # the receiver, added last

    send_together(sim, second, first)

    assert heard_by_receiver(sim, capsys) == [first.radio_node, second.radio_node]


def test_sends_on_one_tick_take_one_tick_each_to_read(sim, capsys):
    red, green = add_in_radio_mode(sim, "red", "green")
    add_in_radio_mode(sim, "blue")  # the receiver, added last
    send_together(sim, red, green)
    capsys.readouterr()
    sim.advance(TICK)
    capsys.readouterr()

    sim.advance(TICK)

    assert heard_from(capsys.readouterr().out) == [green.radio_node]


# ---------------------------------------------------------------------------
# Nodes
# ---------------------------------------------------------------------------


def test_each_device_gets_its_own_radio_node_in_add_order(sim):
    devices = [sim.add_device(name, scene="hardware_test") for name in ("red", "blue", "green")]

    assert [d.radio_node for d in devices] == [1, 2, 3]


def test_a_received_packet_names_its_senders_node(sim, capsys):
    _red, _blue, green = add_in_radio_mode(sim, "red", "blue", "green")
    capsys.readouterr()

    green.tap("A")

    assert heard_from(capsys.readouterr().out) == [green.radio_node, green.radio_node]


# ---------------------------------------------------------------------------
# Recordings
# ---------------------------------------------------------------------------


def test_radio_sent_records_when_each_packet_went_out_and_what_it_carried(sim):
    red, _blue = add_in_radio_mode(sim, "red", "blue")
    red.forget()

    red.schedule_hold("A")
    sim.run_until(lambda: bool(red.radio_sent))

    assert red.radio_sent == [RadioSent(sim.now, HW_TEST_PAYLOAD)]


def test_forget_clears_radio_sent(sim):
    red, _blue = add_in_radio_mode(sim, "red", "blue")
    red.tap("A")

    red.forget()

    assert red.radio_sent == []


# ---------------------------------------------------------------------------
# Outside senders
# ---------------------------------------------------------------------------


def test_receive_radio_lands_a_packet_on_the_next_tick(sim):
    (blue,) = add_in_radio_mode(sim, "blue")

    blue.receive_radio(HW_TEST_PAYLOAD, sender=7)
    flashed_before_a_tick = flashed(blue)
    sim.advance(TICK)

    assert not flashed_before_a_tick
    assert flashed(blue)


def test_receive_radio_names_the_sender_given(sim, capsys):
    (blue,) = add_in_radio_mode(sim, "blue")
    capsys.readouterr()

    blue.receive_radio(HW_TEST_PAYLOAD, sender=7)
    sim.advance(TICK)

    assert heard_from(capsys.readouterr().out) == [7]
