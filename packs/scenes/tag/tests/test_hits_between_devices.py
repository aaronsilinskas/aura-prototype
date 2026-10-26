"""Tag shots between two simulated devices, carried by the IR medium.

Red aims its line emitter, then pulls the trigger; blue's real IR stack
decodes whatever reaches it. Friendly-fire and team rules stay in the
single-device ``receive_ir`` tests in ``test_hit.py``.
"""

from __future__ import annotations

from engine.network import LINE
from packs.scenes.tag.tests.helpers import SHOOTER, start_game


def test_when_red_shoots_blue_blue_registers_the_hit(sim):
    red = sim.add_device("red", scene="tag", scene_data=SHOOTER)
    blue = sim.add_device("blue", scene="tag", scene_data=SHOOTER)
    start_game(sim, red, blue)

    red.aim(LINE, at=blue)
    red.tap("A")
    sim.advance(0.1)

    assert blue.has_played("scene.hit_start")


def test_a_shot_aimed_at_nobody_hits_no_one(sim):
    red = sim.add_device("red", scene="tag", scene_data=SHOOTER)
    blue = sim.add_device("blue", scene="tag", scene_data=SHOOTER)
    start_game(sim, red, blue)

    red.tap("A")
    sim.advance(0.1)

    assert not blue.has_played("scene.hit_start")
