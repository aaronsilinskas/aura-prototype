"""The IR medium: how aimed IR reaches other simulated devices, and when.

Driven through Tag, whose hit sound is stamped with the tick that decoded the
shot, and through the IR range pair, whose transmitter sends on its own.
"""

from __future__ import annotations

import pytest

from app.simulation import TICK, SimulatedDevice, Simulation
from engine.network import LINE
from engine.state import Scope

# SHOOTER and start_game copy Tag's test helpers: the harness's tests stand on no scene's tests.
SHOOTER: dict[str, object] = {"tag_expected_team": 2, "tag_expected_player": 3}
"""The team/player a Tag device both fires as and counts hits from."""

BYSTANDER: dict[str, object] = {"tag_expected_team": 1, "tag_expected_player": 1}
"""Fires a tag a ``SHOOTER`` device ignores."""

RED = 0xFF0000


@pytest.fixture()
def sim() -> Simulation:
    return Simulation()


def start_game(sim: Simulation, *players: SimulatedDevice) -> None:
    for player in players:
        player.tap("A")
    sim.run_until(lambda: all(p.has_played("scene.go_start") for p in players))
    for player in players:
        player.forget()


def fire_together(sim: Simulation, *shooters: SimulatedDevice) -> float:
    """Pull every shooter's trigger on the same tick; return when the shots went out."""
    for shooter in shooters:
        shooter.hold("A")
    sim.run_until(lambda: all(s.ir_sent for s in shooters))
    (at,) = {s.ir_sent[0].at for s in shooters}
    return at


def hit_at(player: SimulatedDevice) -> float:
    (hit,) = [p.at for p in player.played if p.clip == "scene.hit_start"]
    return hit


def add_in_order(sim: Simulation, receiver_first: bool) -> tuple[SimulatedDevice, SimulatedDevice]:
    """A red shooter and the blue device it aims at, added in the order given."""
    if receiver_first:
        blue = sim.add_device("blue", scene="tag", scene_data=SHOOTER)
        red = sim.add_device("red", scene="tag", scene_data=SHOOTER)
    else:
        red = sim.add_device("red", scene="tag", scene_data=SHOOTER)
        blue = sim.add_device("blue", scene="tag", scene_data=SHOOTER)
    return red, blue


# ---------------------------------------------------------------------------
# Delivery
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("receiver_first", [False, True], ids=["sender-first", "receiver-first"])
def test_a_shot_is_decoded_on_the_tick_after_it_was_sent_whatever_the_add_order(
    sim, receiver_first
):
    red, blue = add_in_order(sim, receiver_first)
    start_game(sim, red, blue)
    red.aim(LINE, at=blue)

    sent = fire_together(sim, red)
    sim.advance(0.1)

    assert hit_at(blue) == pytest.approx(sent + TICK)


def test_two_senders_shots_on_one_tick_both_decode(sim):
    # Each matching one-damage tag takes one of ten pips off the hitpoint bar.
    red = sim.add_device("red", scene="tag", scene_data=SHOOTER)
    green = sim.add_device("green", scene="tag", scene_data=SHOOTER)
    blue = sim.add_device("blue", scene="tag", scene_data={**SHOOTER, "tag_starting_hitpoints": 10})
    start_game(sim, red, green, blue)
    red.aim(LINE, at=blue)
    green.aim(LINE, at=blue)

    fire_together(sim, red, green)
    sim.advance(0.1)

    assert blue.strip(Scope.PERSONAL).lit == 8


@pytest.mark.parametrize(
    ("matching_first", "ticks_late"),
    [(True, 1), (False, 2)],
    ids=["matching-first", "matching-second"],
)
def test_shots_sent_on_one_tick_decode_in_sender_add_order(sim, matching_first, ticks_late):
    if matching_first:
        matching = sim.add_device("red", scene="tag", scene_data=SHOOTER)
        other = sim.add_device("green", scene="tag", scene_data=BYSTANDER)
    else:
        other = sim.add_device("green", scene="tag", scene_data=BYSTANDER)
        matching = sim.add_device("red", scene="tag", scene_data=SHOOTER)
    blue = sim.add_device("blue", scene="tag", scene_data=SHOOTER)
    start_game(sim, matching, other, blue)
    matching.aim(LINE, at=blue)
    other.aim(LINE, at=blue)

    sent = fire_together(sim, matching, other)
    sim.advance(0.1)

    assert hit_at(blue) == pytest.approx(sent + ticks_late * TICK)


def test_a_shot_already_in_flight_lands_where_it_was_aimed(sim):
    red, blue = add_in_order(sim, receiver_first=False)
    start_game(sim, red, blue)
    red.aim(LINE, at=blue)
    fire_together(sim, red)

    red.aim(LINE, at=None)
    sim.advance(0.1)

    assert blue.has_played("scene.hit_start")


def test_an_aim_at_several_devices_reaches_each_of_them(sim):
    red = sim.add_device("red", scene="tag", scene_data=SHOOTER)
    blue = sim.add_device("blue", scene="tag", scene_data=SHOOTER)
    green = sim.add_device("green", scene="tag", scene_data=SHOOTER)
    start_game(sim, red, blue, green)

    red.aim(LINE, at=[blue, green])
    red.tap("A")
    sim.advance(0.1)

    assert blue.has_played("scene.hit_start")
    assert green.has_played("scene.hit_start")


def test_a_receiver_subset_surfaces_as_the_best_receiver(sim):
    transmitter = sim.add_device("tx", scene="ir_range_transmitter")
    receiver = sim.add_device("rx", scene="ir_range_receiver")

    transmitter.aim(LINE, at=receiver, receivers=[2])
    sim.advance(0.1)

    assert receiver.best_receiver == 2


def test_a_shot_in_another_wire_frame_codec_is_not_decoded(sim):
    # Tag speaks the Tag wire-frame; the range receiver decodes only the Aura
    # one. Blue, hit by the same shot, shows it did land.
    red = sim.add_device("red", scene="tag", scene_data=SHOOTER)
    blue = sim.add_device("blue", scene="tag", scene_data=SHOOTER)
    receiver = sim.add_device("rx", scene="ir_range_receiver")
    start_game(sim, red, blue)

    red.aim(LINE, at=[blue, receiver])
    red.tap("A")
    sim.advance(0.1)

    assert blue.has_played("scene.hit_start")
    assert receiver.strip(Scope.PERSONAL).all_lit(RED)


# ---------------------------------------------------------------------------
# Raises
# ---------------------------------------------------------------------------


def test_a_device_cannot_aim_at_itself(sim):
    red = sim.add_device("red", scene="tag")

    with pytest.raises(ValueError, match="itself"):
        red.aim(LINE, at=red)


def test_an_emitter_the_device_does_not_wire_cannot_be_aimed(sim):
    # The simulated device wires every emitter, so only an unknown one is unwired.
    red = sim.add_device("red", scene="tag")
    blue = sim.add_device("blue", scene="tag")

    with pytest.raises(ValueError, match="emitter"):
        red.aim("laser", at=blue)


def test_a_device_cannot_aim_at_a_device_in_another_simulation(sim):
    red = sim.add_device("red", scene="tag")
    blue = Simulation().add_device("blue", scene="tag")

    with pytest.raises(ValueError, match="another Simulation"):
        red.aim(LINE, at=blue)


def test_an_aim_cannot_reach_a_receiver_the_device_lacks(sim):
    red = sim.add_device("red", scene="tag")
    blue = sim.add_device("blue", scene="tag")

    with pytest.raises(ValueError, match="receivers"):
        red.aim(LINE, at=blue, receivers=[3])
