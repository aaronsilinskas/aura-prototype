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
from packs.scenes.tag.tests.helpers import AMMO_AMBER, RED, SHOOTER, shots, start_game

TWO_ROUNDS = {"tag_max_ammo": 2, "tag_shot_cooldown": 0.3, "tag_reload_duration": 1.0}
"""A short magazine and reload, so running dry and reloading stay quick."""


# ---------------------------------------------------------------------------
# Firing
# ---------------------------------------------------------------------------


def test_pressing_a_fires_the_players_own_tag_on_the_line_emitter(simulation):
    player = simulation.add_device("red", scene="tag", scene_data=SHOOTER)
    start_game(simulation, player)

    player.tap("A")

    assert shots(player) == [(2, 3, 1)]


def test_a_shot_flashes_the_directional_strip_white(simulation):
    player = simulation.add_device("red", scene="tag")
    start_game(simulation, player)

    player.tap("A")

    assert player.strip(Scope.DIRECTIONAL).all_lit(0xFFFFFF)


def test_a_shot_plays_the_fire_sound(simulation):
    player = simulation.add_device("red", scene="tag")
    start_game(simulation, player)

    player.tap("A")

    assert player.has_played("scene.fire_shot_start")


def test_a_shot_clicks_the_haptic(simulation):
    player = simulation.add_device("red", scene="tag")
    start_game(simulation, player)

    player.tap("A")

    assert [b.pattern for b in player.buzzed] == [(HapticPattern.STRONG_CLICK,)]


def test_the_fire_flash_goes_dark_when_the_fire_sound_ends(simulation):
    player = simulation.add_device("red", scene="tag")
    start_game(simulation, player)

    player.tap("A")
    simulation.advance(player.clip_length("scene.fire_shot_start"))

    assert player.strip(Scope.DIRECTIONAL).dark


def test_a_shot_drains_one_pip_from_the_full_amber_ammo_bar(simulation):
    player = simulation.add_device("red", scene="tag", scene_data={"tag_max_ammo": 10})
    start_game(simulation, player)

    player.tap("A")

    bar = player.strip(Scope.Global.BUFF)
    assert bar.lit == bar.size - bar.size // 10
    assert set(bar.pixels) <= {0, AMMO_AMBER}


def test_an_idle_trigger_sends_nothing(simulation):
    player = simulation.add_device("red", scene="tag")
    start_game(simulation, player)

    simulation.advance(2.0)

    assert shots(player) == []
    assert player.played == []


def test_pressing_a_before_the_game_starts_counts_down_instead_of_firing(simulation):
    player = simulation.add_device(
        "red", scene="tag", scene_data={"tag_warning_pulse_duration": 0.6}
    )

    player.tap("A")
    simulation.advance(0.6)

    assert shots(player) == []
    assert player.has_played("scene.warning_pulse_peak")


# ---------------------------------------------------------------------------
# Cooldown
# ---------------------------------------------------------------------------


def test_a_second_press_inside_the_cooldown_is_swallowed(simulation):
    player = simulation.add_device("red", scene="tag", scene_data={"tag_shot_cooldown": 1.0})
    start_game(simulation, player)

    player.tap("A")
    player.tap("A")

    assert len(shots(player)) == 1


def test_a_press_after_the_cooldown_fires_again(simulation):
    player = simulation.add_device("red", scene="tag", scene_data={"tag_shot_cooldown": 0.3})
    start_game(simulation, player)

    player.tap("A")
    simulation.advance(0.3)
    player.tap("A")

    assert len(shots(player)) == 2


# ---------------------------------------------------------------------------
# Running dry and reloading
# ---------------------------------------------------------------------------


def empty_the_magazine(simulation: Simulation, player: SimulatedDevice) -> None:
    for _ in range(TWO_ROUNDS["tag_max_ammo"]):
        player.tap("A")
        simulation.advance(TWO_ROUNDS["tag_shot_cooldown"])
    player.forget()


def reload_fully(simulation: Simulation, player: SimulatedDevice) -> None:
    player.hold("A")
    simulation.advance(TWO_ROUNDS["tag_reload_duration"])
    player.release("A")


def abandon_reload(simulation: Simulation, player: SimulatedDevice) -> None:
    player.hold("A")
    simulation.advance(TWO_ROUNDS["tag_reload_duration"] / 2)
    player.release("A")
    simulation.advance(TWO_ROUNDS["tag_reload_duration"])


def pulsing_red(strip: Strip) -> bool:
    return not strip.dark and strip.shades_of(RED)


def test_firing_the_last_round_pulses_the_ammo_bar_red(simulation):
    player = simulation.add_device("red", scene="tag", scene_data=TWO_ROUNDS)
    start_game(simulation, player)

    empty_the_magazine(simulation, player)

    assert pulsing_red(player.strip(Scope.Global.BUFF))


def test_pressing_with_an_empty_magazine_dry_fires_instead_of_shooting(simulation):
    player = simulation.add_device("red", scene="tag", scene_data=TWO_ROUNDS)
    start_game(simulation, player)
    empty_the_magazine(simulation, player)

    player.hold("A")

    assert shots(player) == []
    assert player.has_played("scene.dry_fire_start")


def test_a_dry_fire_bumps_the_haptic_softly(simulation):
    player = simulation.add_device("red", scene="tag", scene_data=TWO_ROUNDS)
    start_game(simulation, player)
    empty_the_magazine(simulation, player)

    player.hold("A")

    assert [b.pattern for b in player.buzzed] == [(HapticPattern.SOFT_BUMP,)]


def test_pressing_with_an_empty_magazine_starts_reloading(simulation):
    player = simulation.add_device("red", scene="tag", scene_data=TWO_ROUNDS)
    start_game(simulation, player)
    empty_the_magazine(simulation, player)

    player.hold("A")

    assert player.has_played("scene.reload")


def test_holding_the_trigger_that_fired_the_last_round_does_not_start_a_reload(simulation):
    player = simulation.add_device(
        "red", scene="tag", scene_data={"tag_max_ammo": 1, "tag_shot_cooldown": 0.3}
    )
    start_game(simulation, player)

    player.hold("A")
    simulation.advance(1.0)

    assert len(shots(player)) == 1
    assert not player.has_played("scene.reload")


def test_a_fresh_press_right_after_the_last_round_reloads_despite_the_cooldown(simulation):
    player = simulation.add_device(
        "red", scene="tag", scene_data={"tag_max_ammo": 1, "tag_shot_cooldown": 1.0}
    )
    start_game(simulation, player)

    player.tap("A")
    player.hold("A")  # registers well inside the cooldown the last round started

    assert len(shots(player)) == 1
    assert player.has_played("scene.reload")


def test_holding_through_the_reload_plays_the_reload_complete_sound(simulation):
    player = simulation.add_device("red", scene="tag", scene_data=TWO_ROUNDS)
    start_game(simulation, player)
    empty_the_magazine(simulation, player)

    reload_fully(simulation, player)

    assert player.has_played("scene.reload_complete")


def test_holding_through_the_reload_double_clicks_the_haptic(simulation):
    player = simulation.add_device("red", scene="tag", scene_data=TWO_ROUNDS)
    start_game(simulation, player)
    empty_the_magazine(simulation, player)

    reload_fully(simulation, player)

    assert player.buzzed[-1].pattern == (HapticPattern.DOUBLE_CLICK,)


def test_the_ammo_bar_fills_red_as_the_reload_is_held(simulation):
    player = simulation.add_device("red", scene="tag", scene_data=TWO_ROUNDS)
    start_game(simulation, player)
    empty_the_magazine(simulation, player)

    player.hold("A")
    simulation.advance(TWO_ROUNDS["tag_reload_duration"] / 4)
    early = player.strip(Scope.Global.BUFF)
    simulation.advance(TWO_ROUNDS["tag_reload_duration"] / 2)
    later = player.strip(Scope.Global.BUFF)

    assert 0 < early.lit < later.lit < later.size
    assert early.shades_of(RED) and later.shades_of(RED)


def test_holding_through_the_reload_refills_the_amber_ammo_bar(simulation):
    player = simulation.add_device("red", scene="tag", scene_data=TWO_ROUNDS)
    start_game(simulation, player)
    empty_the_magazine(simulation, player)

    reload_fully(simulation, player)

    assert player.strip(Scope.Global.BUFF).all_lit(AMMO_AMBER)


def test_a_press_after_a_full_reload_fires_again(simulation):
    player = simulation.add_device("red", scene="tag", scene_data=TWO_ROUNDS)
    start_game(simulation, player)
    empty_the_magazine(simulation, player)
    reload_fully(simulation, player)

    player.tap("A")

    assert len(shots(player)) == 1


def test_the_trigger_still_held_after_a_reload_does_not_auto_fire(simulation):
    player = simulation.add_device("red", scene="tag", scene_data=TWO_ROUNDS)
    start_game(simulation, player)
    empty_the_magazine(simulation, player)

    player.hold("A")
    simulation.advance(TWO_ROUNDS["tag_reload_duration"] + 2.0)

    assert shots(player) == []


def test_letting_go_before_the_reload_finishes_never_completes_it(simulation):
    player = simulation.add_device("red", scene="tag", scene_data=TWO_ROUNDS)
    start_game(simulation, player)
    empty_the_magazine(simulation, player)

    abandon_reload(simulation, player)

    assert not player.has_played("scene.reload_complete")


def test_letting_go_before_the_reload_finishes_returns_the_bar_to_pulsing_red(simulation):
    player = simulation.add_device("red", scene="tag", scene_data=TWO_ROUNDS)
    start_game(simulation, player)
    empty_the_magazine(simulation, player)

    abandon_reload(simulation, player)

    assert pulsing_red(player.strip(Scope.Global.BUFF))


def test_a_press_after_an_abandoned_reload_dry_fires(simulation):
    player = simulation.add_device("red", scene="tag", scene_data=TWO_ROUNDS)
    start_game(simulation, player)
    empty_the_magazine(simulation, player)
    abandon_reload(simulation, player)
    player.forget()

    player.tap("A")

    assert shots(player) == []
    assert player.has_played("scene.dry_fire_start")


# ---------------------------------------------------------------------------
# More than one device
# ---------------------------------------------------------------------------


def test_one_players_trigger_never_fires_another_players_blaster(simulation):
    red = simulation.add_device("red", scene="tag", scene_data=SHOOTER)
    blue = simulation.add_device("blue", scene="tag", scene_data={"tag_expected_team": 1})
    start_game(simulation, red, blue)

    red.tap("A")

    assert shots(red) == [(2, 3, 1)]
    assert shots(blue) == []
