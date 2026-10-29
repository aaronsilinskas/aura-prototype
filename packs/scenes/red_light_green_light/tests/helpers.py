"""Shared moves and reads for the Red Light Green Light simulation tests."""

from __future__ import annotations

from app.simulation import TICK, SimulatedDevice, Simulation
from engine.state import Scope

RED = 0xFF0000
GREEN = 0x00FF00
YELLOW = 0xFFFF00

LEVEL_BAR = Scope.AMBIENT
LIGHT_STRIPS = [
    Scope.Global.BUFF,
    Scope.Global.DEBUFF,
    Scope.Global.MAIN,
    Scope.PERSONAL,
    Scope.DIRECTIONAL,
]
"""Every strip but the level bar: where the lights, warnings and level-up show."""
EVERY_STRIP = [*LIGHT_STRIPS, LEVEL_BAR]

READY_SOUND = "scene.ready_start"
WARNING_PEAK = "scene.warning_sting_peak"
RED_MUSIC = "scene.red_light_music_start"
GREEN_MUSIC = "scene.green_light_music_start"
LEVEL_UP_SOUND = "scene.level_up_start"
WIN_STING = "scene.win_sting_start"
GAME_OVER_STING = "basic.game_over_sting_start"

SLACK = TICK
"""How far a timed phase change, or a clip running out, may trail its tunable.

Both are checked once a tick, so they land on the first tick at or past it.
One that falls on a tick boundary can land a tick later still: the clock sums
``TICK`` tick by tick, and the sum can fall a hair short of the boundary.
"""

CLIP_END_SLACK = 2 * TICK
"""How far a phase change that waits on a clip running out may trail the clip's length.

The clip is seen to have run out on the first tick at or past its end, and the
phase changes on the tick after that one.
"""

QUICK_WARNINGS = {"rlgl_warning_pulse_max": 0.2, "rlgl_warning_pulse_min": 0.2}
"""Three 0.2 s pulses, so a warning is over in 0.6 s at every level."""


def times_played(player: SimulatedDevice, clip: str) -> int:
    return sum(1 for p in player.played if p.clip == clip)


def last_played_at(player: SimulatedDevice, clip: str) -> float:
    return [p.at for p in player.played if p.clip == clip][-1]


def wait_for(simulation: Simulation, player: SimulatedDevice, clip: str) -> None:
    """Run until *clip* next starts playing on *player*."""
    before = times_played(player, clip)
    simulation.run_until(lambda: times_played(player, clip) > before, timeout=30.0)


def lit_in(player: SimulatedDevice, color: int) -> bool:
    """Every pixel of every light strip shows exactly *color*."""
    return all(player.strip(scope).all_lit(color) for scope in LIGHT_STRIPS)


def survive_round(simulation: Simulation, player: SimulatedDevice) -> None:
    """Hold still through Red Light and keep moving through Green Light until the round ends.

    Returns at the level-up or the win, with the device held still again.
    """
    player.hold_still()
    wait_for(simulation, player, GREEN_MUSIC)
    player.move()
    ended = times_played(player, LEVEL_UP_SOUND) + times_played(player, WIN_STING)
    simulation.run_until(
        lambda: times_played(player, LEVEL_UP_SOUND) + times_played(player, WIN_STING) > ended,
        timeout=30.0,
    )
    player.hold_still()
