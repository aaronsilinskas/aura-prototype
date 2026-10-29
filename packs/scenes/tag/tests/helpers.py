"""Shared moves and reads for the Tag simulation tests."""

from __future__ import annotations

from app.simulation import TICK, SimulatedDevice, Simulation, Strip
from engine.network import LINE
from engine.state import Scope
from packs.scenes.tag.tag_data import TagData, decode_tag_data, encode_tag_data

AMMO_AMBER = 0xFFBF00
GREEN = 0x00FF00
RED = 0xFF0000

EVERY_STRIP = [
    Scope.Global.BUFF,
    Scope.Global.DEBUFF,
    Scope.Global.MAIN,
    Scope.PERSONAL,
    Scope.DIRECTIONAL,
    Scope.AMBIENT,
]

SHOOTER = {"tag_expected_team": 2, "tag_expected_player": 3}
"""Pins the one team/player whose tags count against a device."""


def start_game(simulation: Simulation, *players: SimulatedDevice) -> None:
    """Ready -> Starting -> Playing through real input, then clear the record."""
    for player in players:
        player.tap("A")
    simulation.run_until(lambda: all(p.has_played("scene.go_start") for p in players))
    for player in players:
        player.forget()


def tag_shot(team: int, player: int, damage: int) -> bytes:
    """The payload of a tag shot from *team*/*player* dealing *damage*."""
    return bytes(encode_tag_data(TagData(team, player, damage)))


def shooters_tag(damage: int = 1) -> bytes:
    """A tag shot from the pinned ``SHOOTER``."""
    return tag_shot(SHOOTER["tag_expected_team"], SHOOTER["tag_expected_player"], damage)


def hit(simulation: Simulation, player: SimulatedDevice, payload: bytes) -> None:
    """Land a tag shot on *player* and run the ticks that react to it.

    The first tick decodes the shot and plays the hit; the second is the
    first input pass to see the hitpoints it left.
    """
    player.receive_ir(payload)
    simulation.advance(2 * TICK)


def fire_together(simulation: Simulation, *shooters: SimulatedDevice) -> None:
    """Pull every shooter's trigger on the same tick, and run until their shots are decoded.

    A shot goes out on the tick its trigger registers and is decoded, wherever
    it was aimed, on the next.
    """
    sent = [len(shooter.ir_sent) for shooter in shooters]
    for shooter in shooters:
        shooter.schedule_hold("A")
    simulation.run_until(
        lambda: all(len(s.ir_sent) > n for s, n in zip(shooters, sent, strict=True))
    )
    for shooter in shooters:
        shooter.schedule_release("A")
    simulation.advance(TICK)


def shots(player: SimulatedDevice) -> list[tuple[int, int, int]]:
    """Every tag shot the player sent on the LINE emitter, as (team, player, damage)."""
    decoded = [decode_tag_data(s.payload) for s in player.ir_sent if s.emitter == LINE]
    return [(d.team, d.player, d.damage) for d in decoded]


def sweeping_red(strip: Strip) -> bool:
    """Part of the strip lit, and only in red: the Ready laser sweep."""
    return 0 < strip.lit < strip.size and strip.shades_of(RED)
