"""PROTOTYPE (#957), throwaway: the Tag shooting tests rewritten on a stub harness.

The question is what these tests should *read like*. Each one boots the real
Tag scene, walks it into Playing through real button presses, and asserts on
what the device observably did: IR sent, clips played, haptics, strip pixels.
Compare with ``packs/scenes/tag/rules/tests/test_shooting_rule.py``.
"""

from __future__ import annotations

import pytest

from app.simulation_prototype.harness import SimulatedDevice, Simulation
from effects.effect import HapticPattern
from engine.network import LINE
from engine.state import Scope
from packs.scenes.tag.tag_data import TagData, decode_tag_data, encode_tag_data

AMMO_AMBER = 0xFFBF00
COUNTDOWN = 5 * 0.6  # Tag's default warning pulses x pulse duration
COOLDOWN = 0.3
RELOAD = 3.0


@pytest.fixture()
def sim() -> Simulation:
    return Simulation()


def start_game(sim: Simulation, *players: SimulatedDevice) -> None:
    """Ready -> Starting -> Playing through real input, then clear the record."""
    for player in players:
        player.tap("A")
    sim.advance(COUNTDOWN + 0.5)
    for player in players:
        assert player.has_played("scene.go_start"), f"{player.name} never reached Playing"
        player.forget()


def shots(player: SimulatedDevice) -> list[tuple[int, int, int]]:
    """Every tag shot the player sent on the LINE emitter, as (team, player, damage)."""
    decoded = [decode_tag_data(s.payload) for s in player.ir_sent if s.emitter == LINE]
    return [(d.team, d.player, d.damage) for d in decoded]


# ---------------------------------------------------------------------------
# Firing
# ---------------------------------------------------------------------------


def test_pressing_a_fires_the_players_own_tag_on_the_line_emitter(sim):
    player = sim.add_device("red", scene="tag")
    start_game(sim, player)

    player.tap("A")
    sim.advance(0.2)

    assert shots(player) == [(0, 1, 1)]


def test_a_shot_flashes_directional_white_plays_the_fire_sound_and_clicks(sim):
    player = sim.add_device("red", scene="tag")
    start_game(sim, player)

    player.tap("A")
    sim.advance(0.2)

    assert player.strip(Scope.DIRECTIONAL).all_lit(0xFFFFFF)
    assert player.has_played("scene.fire_shot_start")
    assert [b.pattern for b in player.buzzed] == [(HapticPattern.STRONG_CLICK,)]


def test_a_shot_drains_one_pip_from_the_amber_ammo_bar(sim):
    player = sim.add_device("red", scene="tag")
    start_game(sim, player)
    assert player.strip(Scope.Global.BUFF).lit == 10

    player.tap("A")
    sim.advance(0.2)

    bar = player.strip(Scope.Global.BUFF)
    assert bar.lit == 9
    assert set(bar.pixels) <= {0, AMMO_AMBER}


def test_an_idle_trigger_sends_nothing(sim):
    player = sim.add_device("red", scene="tag")
    start_game(sim, player)

    sim.advance(2.0)

    assert shots(player) == []
    assert player.played == []


def test_pressing_a_before_the_game_starts_counts_down_instead_of_firing(sim):
    player = sim.add_device("red", scene="tag")

    player.tap("A")
    sim.advance(0.5)

    assert shots(player) == []
    assert player.has_played("scene.warning_pulse_peak")


# ---------------------------------------------------------------------------
# Cooldown
# ---------------------------------------------------------------------------


def test_a_second_press_inside_the_cooldown_is_swallowed(sim):
    player = sim.add_device("red", scene="tag")
    start_game(sim, player)

    player.tap("A", hold_for=0.08)  # a real tap must outlast the 50 ms debounce...
    sim.advance(0.15)  # ...and so must the release, or the next tap never registers
    player.tap("A", hold_for=0.08)  # registers ~0.15 s after the first: inside the cooldown
    sim.advance(0.1)

    assert len(shots(player)) == 1


def test_a_press_after_the_cooldown_fires_again(sim):
    player = sim.add_device("red", scene="tag")
    start_game(sim, player)

    player.tap("A")
    sim.advance(COOLDOWN + 0.1)
    player.tap("A")
    sim.advance(0.2)

    assert len(shots(player)) == 2


# ---------------------------------------------------------------------------
# Running dry and reloading (a 2-round magazine keeps these short)
# ---------------------------------------------------------------------------


def empty_the_magazine(sim: SimulatedDevice | Simulation, player: SimulatedDevice) -> None:
    for _ in range(2):
        player.tap("A")
        sim.advance(COOLDOWN + 0.1)
    assert len(shots(player)) == 2
    player.forget()


def test_firing_the_last_round_pulses_the_ammo_bar_red(sim):
    player = sim.add_device("red", scene="tag", scene_data={"tag_max_ammo": 2})
    start_game(sim, player)

    empty_the_magazine(sim, player)
    sim.advance(0.3)

    bar = player.strip(Scope.Global.BUFF)
    assert AMMO_AMBER not in bar.pixels
    assert any(p & 0xFF0000 and not p & 0x00FFFF for p in bar.pixels)  # some red, nothing else


def test_pressing_with_an_empty_magazine_dry_fires_and_starts_reloading(sim):
    player = sim.add_device("red", scene="tag", scene_data={"tag_max_ammo": 2})
    start_game(sim, player)
    empty_the_magazine(sim, player)

    player.hold("A")
    sim.advance(0.2)

    assert shots(player) == []
    assert player.has_played("scene.dry_fire_start")
    assert player.has_played("scene.reload")


def test_holding_the_trigger_that_fired_the_last_round_does_not_start_a_reload(sim):
    player = sim.add_device("red", scene="tag", scene_data={"tag_max_ammo": 1})
    start_game(sim, player)

    player.hold("A")
    sim.advance(1.0)

    assert len(shots(player)) == 1
    assert not player.has_played("scene.reload")


def test_holding_through_the_reload_refills_the_magazine(sim):
    player = sim.add_device("red", scene="tag", scene_data={"tag_max_ammo": 2})
    start_game(sim, player)
    empty_the_magazine(sim, player)

    player.hold("A")
    sim.advance(RELOAD + 0.2)
    player.release("A")
    sim.advance(0.1)

    assert player.has_played("scene.reload_complete")
    assert player.strip(Scope.Global.BUFF).lit == 10
    player.tap("A")
    sim.advance(0.2)
    assert len(shots(player)) == 1


def test_the_trigger_still_held_after_a_reload_does_not_auto_fire(sim):
    player = sim.add_device("red", scene="tag", scene_data={"tag_max_ammo": 2})
    start_game(sim, player)
    empty_the_magazine(sim, player)

    player.hold("A")
    sim.advance(RELOAD + 2.0)

    assert shots(player) == []


def test_letting_go_before_the_reload_finishes_leaves_the_magazine_empty(sim):
    player = sim.add_device("red", scene="tag", scene_data={"tag_max_ammo": 2})
    start_game(sim, player)
    empty_the_magazine(sim, player)

    player.tap("A", hold_for=1.0)
    sim.advance(RELOAD + 0.5)

    assert not player.has_played("scene.reload_complete")
    player.forget()
    player.tap("A")
    sim.advance(0.2)
    assert shots(player) == []
    assert player.has_played("scene.dry_fire_start")


# ---------------------------------------------------------------------------
# Multi-device readiness: one clock, many devices, IR in by injection
# ---------------------------------------------------------------------------


def test_one_players_trigger_never_fires_another_players_blaster(sim):
    red = sim.add_device("red", scene="tag")
    blue = sim.add_device("blue", scene="tag", scene_data={"tag_expected_team": 1})
    start_game(sim, red, blue)

    red.tap("A")
    sim.advance(0.2)

    assert shots(red) == [(0, 1, 1)]
    assert shots(blue) == []


def test_an_incoming_matching_tag_plays_the_hit_on_the_main_strip(sim):
    player = sim.add_device("red", scene="tag")
    start_game(sim, player)

    player.receive_ir(bytes(encode_tag_data(TagData(0, 1, 1))))
    sim.advance(0.1)

    assert player.has_played("scene.hit_start")
    assert not player.strip(Scope.Global.MAIN).dark
