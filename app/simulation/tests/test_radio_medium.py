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


def add_in_radio_mode(simulation: Simulation, *names: str) -> list[SimulatedDevice]:
    devices = [simulation.add_device(name, scene="hardware_test") for name in names]
    for device in devices:
        for _ in range(RADIO_MODE):
            device.tap("B")
    return devices


def heard_from(serial: str) -> list[int]:
    """The sender node of each packet the serial output reports, in order."""
    return [int(node) for node in re.findall(r"radio received .* from (\d+)", serial)]


def flashed(device: SimulatedDevice) -> bool:
    return device.strip(Scope.Global.MAIN).all_lit(GREEN)


def send_together(simulation: Simulation, *senders: SimulatedDevice) -> None:
    """Press A on every sender on the same tick, and run until each has sent."""
    for sender in senders:
        sender.forget()
        sender.schedule_hold("A")
    simulation.run_until(lambda: all(s.radio_sent for s in senders))
    assert len({s.radio_sent[0].at for s in senders}) == 1, "the senders sent on different ticks"


def heard_by_receiver(simulation: Simulation, capsys: pytest.CaptureFixture[str]) -> list[int]:
    """Tick until every packet is read; return the senders the last-added device heard, in order.

    For two senders and one receiver added after them. Every device ticks in
    add order, so the receiver's line ends each tick's output; each sender
    hears the other's one packet on the first tick, so later lines are the
    receiver's alone.
    """
    capsys.readouterr()
    simulation.advance(TICK)
    heard = heard_from(capsys.readouterr().out)[-1:]
    for _ in range(3):
        simulation.advance(TICK)
        heard += heard_from(capsys.readouterr().out)
    return heard


# ---------------------------------------------------------------------------
# Reach
# ---------------------------------------------------------------------------


def test_a_send_reaches_every_other_device(simulation):
    red, blue, green = add_in_radio_mode(simulation, "red", "blue", "green")

    red.tap("A")

    assert flashed(blue)
    assert flashed(green)


def test_a_device_never_hears_its_own_send(simulation):
    red, _blue = add_in_radio_mode(simulation, "red", "blue")

    red.tap("A")

    assert not flashed(red)


@pytest.mark.parametrize("receiver_first", [False, True], ids=["sender-first", "receiver-first"])
def test_a_send_lands_on_the_tick_after_it_was_sent_whatever_the_add_order(
    simulation, receiver_first
):
    names = ("blue", "red") if receiver_first else ("red", "blue")
    devices = dict(zip(names, add_in_radio_mode(simulation, *names), strict=True))
    red, blue = devices["red"], devices["blue"]

    red.schedule_hold("A")
    simulation.run_until(lambda: bool(red.radio_sent))
    flashed_on_the_send_tick = flashed(blue)
    simulation.advance(TICK)

    assert not flashed_on_the_send_tick
    assert flashed(blue)


# ---------------------------------------------------------------------------
# Queueing
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("red_first", [True, False], ids=["red-added-first", "green-added-first"])
def test_sends_on_one_tick_reach_a_receiver_in_sender_add_order(simulation, capsys, red_first):
    names = ("red", "green") if red_first else ("green", "red")
    first, second = add_in_radio_mode(simulation, *names)
    add_in_radio_mode(simulation, "blue")  # the receiver, added last

    send_together(simulation, second, first)

    assert heard_by_receiver(simulation, capsys) == [first.radio_node, second.radio_node]


def test_sends_on_one_tick_take_one_tick_each_to_read(simulation, capsys):
    red, green = add_in_radio_mode(simulation, "red", "green")
    add_in_radio_mode(simulation, "blue")  # the receiver, added last
    send_together(simulation, red, green)
    capsys.readouterr()
    simulation.advance(TICK)
    capsys.readouterr()

    simulation.advance(TICK)

    assert heard_from(capsys.readouterr().out) == [green.radio_node]


# ---------------------------------------------------------------------------
# Nodes
# ---------------------------------------------------------------------------


def test_each_device_gets_its_own_radio_node_in_add_order(simulation):
    devices = [
        simulation.add_device(name, scene="hardware_test") for name in ("red", "blue", "green")
    ]

    assert [d.radio_node for d in devices] == [1, 2, 3]


def test_a_received_packet_names_its_senders_node(simulation, capsys):
    _red, _blue, green = add_in_radio_mode(simulation, "red", "blue", "green")
    capsys.readouterr()

    green.tap("A")

    assert heard_from(capsys.readouterr().out) == [green.radio_node, green.radio_node]


# ---------------------------------------------------------------------------
# Recordings
# ---------------------------------------------------------------------------


def test_radio_sent_records_when_each_packet_went_out_and_what_it_carried(simulation):
    red, _blue = add_in_radio_mode(simulation, "red", "blue")
    red.forget()

    red.schedule_hold("A")
    simulation.run_until(lambda: bool(red.radio_sent))

    assert red.radio_sent == [RadioSent(simulation.now, HW_TEST_PAYLOAD)]


def test_forget_clears_radio_sent(simulation):
    red, _blue = add_in_radio_mode(simulation, "red", "blue")
    red.tap("A")

    red.forget()

    assert red.radio_sent == []


# ---------------------------------------------------------------------------
# Outside senders
# ---------------------------------------------------------------------------


def test_receive_radio_lands_a_packet_on_the_next_tick(simulation):
    (blue,) = add_in_radio_mode(simulation, "blue")

    blue.receive_radio(HW_TEST_PAYLOAD, sender=7)
    flashed_before_a_tick = flashed(blue)
    simulation.advance(TICK)

    assert not flashed_before_a_tick
    assert flashed(blue)


def test_receive_radio_names_the_sender_given(simulation, capsys):
    (blue,) = add_in_radio_mode(simulation, "blue")
    capsys.readouterr()

    blue.receive_radio(HW_TEST_PAYLOAD, sender=7)
    simulation.advance(TICK)

    assert heard_from(capsys.readouterr().out) == [7]
