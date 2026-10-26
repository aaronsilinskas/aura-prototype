"""Shared moves for the Tag simulation tests: start a game, land a tag, read shots."""

from __future__ import annotations

from app.simulation import SimulatedDevice, Simulation
from engine.network import LINE
from packs.scenes.tag.tag_data import TagData, decode_tag_data, encode_tag_data


def start_game(sim: Simulation, *players: SimulatedDevice) -> None:
    """Ready -> Starting -> Playing through real input, then clear the record."""
    for player in players:
        player.tap("A")
    sim.run_until(lambda: all(p.has_played("scene.go_start") for p in players))
    for player in players:
        player.forget()


def tag(team: int, player: int, damage: int) -> bytes:
    """The payload of a tag shot from *team*/*player* dealing *damage*."""
    return bytes(encode_tag_data(TagData(team, player, damage)))


def shots(player: SimulatedDevice) -> list[tuple[int, int, int]]:
    """Every tag shot the player sent on the LINE emitter, as (team, player, damage)."""
    decoded = [decode_tag_data(s.payload) for s in player.ir_sent if s.emitter == LINE]
    return [(d.team, d.player, d.damage) for d in decoded]
