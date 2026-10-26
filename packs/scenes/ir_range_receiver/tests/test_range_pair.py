"""The IR range pair: a transmitter's shots reach a receiver through the IR medium.

The transmitter scene sends on its own; a test only aims it. Every assertion
reads what the receiver's strips show.
"""

from __future__ import annotations

from engine.network import LINE
from engine.state import Scope

RED = 0xFF0000
GREEN = 0x00FF00

SILENCE_TIMEOUT = 0.5

METER = {
    "ir_range_window_seconds": 1.0,
    "ir_range_silence_timeout": SILENCE_TIMEOUT,
    "ir_range_green_threshold": 1.0,
}
"""A one-second window that goes quiet after ``SILENCE_TIMEOUT``, green only when nothing drops."""

TEN_HZ = {"irtx_send_rate_hz": 10.0}
"""A send every 0.1 s: well inside ``SILENCE_TIMEOUT``."""


def test_a_receiver_the_transmitter_is_aimed_at_shows_solid_green(sim):
    transmitter = sim.add_device("tx", scene="ir_range_transmitter", scene_data=TEN_HZ)
    receiver = sim.add_device("rx", scene="ir_range_receiver", scene_data=METER)

    transmitter.aim(LINE, at=receiver)
    sim.advance(0.5)

    assert receiver.strip(Scope.PERSONAL).all_lit(GREEN)


def test_a_receiver_the_transmitter_turns_away_from_returns_to_solid_red(sim):
    transmitter = sim.add_device("tx", scene="ir_range_transmitter", scene_data=TEN_HZ)
    receiver = sim.add_device("rx", scene="ir_range_receiver", scene_data=METER)
    transmitter.aim(LINE, at=receiver)
    sim.advance(0.5)

    transmitter.aim(LINE, at=None)
    sim.advance(SILENCE_TIMEOUT + 0.1)

    assert receiver.strip(Scope.PERSONAL).all_lit(RED)


def test_the_meter_ignores_which_receiver_heard_the_shot(sim):
    transmitter = sim.add_device("tx", scene="ir_range_transmitter", scene_data=TEN_HZ)
    receiver = sim.add_device("rx", scene="ir_range_receiver", scene_data=METER)

    for index in (0, 1, 2, 0, 1):  # each shot heard by a different receiver
        transmitter.aim(LINE, at=receiver, receivers=[index])
        sim.advance(0.1)

    assert receiver.strip(Scope.PERSONAL).all_lit(GREEN)
