"""Tag shooting, played on simulated devices.

Each test boots the real Tag scene, walks it into Playing through real button
presses, and asserts on what the device observably did: IR sent, clips
played, haptics, strip pixels. A test that depends on a tunable pins it with
``scene_data`` rather than restating the scene's default.
"""

from __future__ import annotations

from app.simulation import SimulatedDevice, Simulation, Strip
from effects.effect import HapticPattern
from engine.state import Scope
from packs.scenes.tag.tests.helpers import AMMO_AMBER, SHOOTER, shots, start_game

TWO_ROUNDS = {"tag_max_ammo": 2, "tag_shot_cooldown": 0.3, "tag_reload_duration": 1.0}
"""A short magazine and reload, so running dry and reloading stay quick."""


# ---------------------------------------------------------------------------
# Firing
# ---------------------------------------------------------------------------


def test_pressing_a_fires_the_players_own_tag_on_the_line_emitter(sim):
    player = sim.add_device("red", scene="tag", scene_data=SHOOTER)
    start_game(sim, player)

    player.tap("A")

    assert shots(player) == [(2, 3, 1)]


def test_a_shot_flashes_the_directional_strip_white(sim):
    player = sim.add_device("red", scene="tag")
    start_game(sim, player)

    player.tap("A")

    assert player.strip(Scope.DIRECTIONAL).all_lit(0xFFFFFF)


def test_a_shot_plays_the_fire_sound(sim):
    player = sim.add_device("red", scene="tag")
    start_game(sim, player)

    player.tap("A")

    assert player.has_played("scene.fire_shot_start")


def test_a_shot_clicks_the_haptic(sim):
    player = sim.add_device("red", scene="tag")
    start_game(sim, player)

    player.tap("A")

    assert [b.pattern for b in player.buzzed] == [(HapticPattern.STRONG_CLICK,)]


def test_the_fire_flash_goes_dark_when_the_fire_sound_ends(sim):
    player = sim.add_device("red", scene="tag")
    start_game(sim, player)

    player.tap("A")
    sim.advance(player.clip_length("scene.fire_shot_start"))

    assert player.strip(Scope.DIRECTIONAL).dark


def test_a_shot_drains_one_pip_from_the_full_amber_ammo_bar(sim):
    player = sim.add_device("red", scene="tag", scene_data={"tag_max_ammo": 10})
    start_game(sim, player)

    player.tap("A")

    bar = player.strip(Scope.Global.BUFF)
    assert bar.lit == bar.size - bar.size // 10
    assert set(bar.pixels) <= {0, AMMO_AMBER}


def test_an_idle_trigger_sends_nothing(sim):
    player = sim.add_device("red", scene="tag")
    start_game(sim, player)

    sim.advance(2.0)

    assert shots(player) == []
    assert player.played == []


def test_pressing_a_before_the_game_starts_counts_down_instead_of_firing(sim):
    player = sim.add_device("red", scene="tag", scene_data={"tag_warning_pulse_duration": 0.6})

    player.tap("A")
    sim.advance(0.6)

    assert shots(player) == []
    assert player.has_played("scene.warning_pulse_peak")


# ---------------------------------------------------------------------------
# Cooldown
# ---------------------------------------------------------------------------


def test_a_second_press_inside_the_cooldown_is_swallowed(sim):
    player = sim.add_device("red", scene="tag", scene_data={"tag_shot_cooldown": 1.0})
    start_game(sim, player)

    player.tap("A")
    player.tap("A")

    assert len(shots(player)) == 1


def test_a_press_after_the_cooldown_fires_again(sim):
    player = sim.add_device("red", scene="tag", scene_data={"tag_shot_cooldown": 0.3})
    start_game(sim, player)

    player.tap("A")
    sim.advance(0.3)
    player.tap("A")

    assert len(shots(player)) == 2


# ---------------------------------------------------------------------------
# Running dry and reloading
# ---------------------------------------------------------------------------


def empty_the_magazine(sim: Simulation, player: SimulatedDevice) -> None:
    for _ in range(TWO_ROUNDS["tag_max_ammo"]):
        player.tap("A")
        sim.advance(TWO_ROUNDS["tag_shot_cooldown"])
    player.forget()


def reload_fully(sim: Simulation, player: SimulatedDevice) -> None:
    player.hold("A")
    sim.advance(TWO_ROUNDS["tag_reload_duration"] + 0.2)
    player.release("A")
    sim.advance(0.2)


def abandon_reload(sim: Simulation, player: SimulatedDevice) -> None:
    player.hold("A")
    sim.advance(TWO_ROUNDS["tag_reload_duration"] / 2)
    player.release("A")
    sim.advance(TWO_ROUNDS["tag_reload_duration"])


def pulsing_red(strip: Strip) -> bool:
    return not strip.dark and all(p & 0x00FFFF == 0 for p in strip.pixels)


def test_firing_the_last_round_pulses_the_ammo_bar_red(sim):
    player = sim.add_device("red", scene="tag", scene_data=TWO_ROUNDS)
    start_game(sim, player)

    empty_the_magazine(sim, player)

    assert pulsing_red(player.strip(Scope.Global.BUFF))


def test_pressing_with_an_empty_magazine_dry_fires_instead_of_shooting(sim):
    player = sim.add_device("red", scene="tag", scene_data=TWO_ROUNDS)
    start_game(sim, player)
    empty_the_magazine(sim, player)

    player.hold("A")
    sim.advance(0.2)

    assert shots(player) == []
    assert player.has_played("scene.dry_fire_start")


def test_pressing_with_an_empty_magazine_starts_reloading(sim):
    player = sim.add_device("red", scene="tag", scene_data=TWO_ROUNDS)
    start_game(sim, player)
    empty_the_magazine(sim, player)

    player.hold("A")
    sim.advance(0.2)

    assert player.has_played("scene.reload")


def test_holding_the_trigger_that_fired_the_last_round_does_not_start_a_reload(sim):
    player = sim.add_device(
        "red", scene="tag", scene_data={"tag_max_ammo": 1, "tag_shot_cooldown": 0.3}
    )
    start_game(sim, player)

    player.hold("A")
    sim.advance(1.0)

    assert len(shots(player)) == 1
    assert not player.has_played("scene.reload")


def test_a_fresh_press_right_after_the_last_round_reloads_despite_the_cooldown(sim):
    player = sim.add_device(
        "red", scene="tag", scene_data={"tag_max_ammo": 1, "tag_shot_cooldown": 1.0}
    )
    start_game(sim, player)

    player.tap("A")
    player.hold("A")  # registers well inside the cooldown the last round started
    sim.advance(0.2)

    assert len(shots(player)) == 1
    assert player.has_played("scene.reload")


def test_holding_through_the_reload_plays_the_reload_complete_sound(sim):
    player = sim.add_device("red", scene="tag", scene_data=TWO_ROUNDS)
    start_game(sim, player)
    empty_the_magazine(sim, player)

    reload_fully(sim, player)

    assert player.has_played("scene.reload_complete")


def test_holding_through_the_reload_refills_the_amber_ammo_bar(sim):
    player = sim.add_device("red", scene="tag", scene_data=TWO_ROUNDS)
    start_game(sim, player)
    empty_the_magazine(sim, player)

    reload_fully(sim, player)

    assert player.strip(Scope.Global.BUFF).all_lit(AMMO_AMBER)


def test_a_press_after_a_full_reload_fires_again(sim):
    player = sim.add_device("red", scene="tag", scene_data=TWO_ROUNDS)
    start_game(sim, player)
    empty_the_magazine(sim, player)
    reload_fully(sim, player)

    player.tap("A")

    assert len(shots(player)) == 1


def test_the_trigger_still_held_after_a_reload_does_not_auto_fire(sim):
    player = sim.add_device("red", scene="tag", scene_data=TWO_ROUNDS)
    start_game(sim, player)
    empty_the_magazine(sim, player)

    player.hold("A")
    sim.advance(TWO_ROUNDS["tag_reload_duration"] + 2.0)

    assert shots(player) == []


def test_letting_go_before_the_reload_finishes_never_completes_it(sim):
    player = sim.add_device("red", scene="tag", scene_data=TWO_ROUNDS)
    start_game(sim, player)
    empty_the_magazine(sim, player)

    abandon_reload(sim, player)

    assert not player.has_played("scene.reload_complete")


def test_letting_go_before_the_reload_finishes_returns_the_bar_to_pulsing_red(sim):
    player = sim.add_device("red", scene="tag", scene_data=TWO_ROUNDS)
    start_game(sim, player)
    empty_the_magazine(sim, player)

    abandon_reload(sim, player)

    assert pulsing_red(player.strip(Scope.Global.BUFF))


def test_a_press_after_an_abandoned_reload_dry_fires(sim):
    player = sim.add_device("red", scene="tag", scene_data=TWO_ROUNDS)
    start_game(sim, player)
    empty_the_magazine(sim, player)
    abandon_reload(sim, player)
    player.forget()

    player.tap("A")

    assert shots(player) == []
    assert player.has_played("scene.dry_fire_start")


# ---------------------------------------------------------------------------
# More than one device
# ---------------------------------------------------------------------------


def test_one_players_trigger_never_fires_another_players_blaster(sim):
    red = sim.add_device("red", scene="tag", scene_data=SHOOTER)
    blue = sim.add_device("blue", scene="tag", scene_data={"tag_expected_team": 1})
    start_game(sim, red, blue)

    red.tap("A")

    assert shots(red) == [(2, 3, 1)]
    assert shots(blue) == []
