"""``ReturnToLobbyRule`` on its own, reading ``hold_seconds`` from the Settings view."""

from __future__ import annotations

from engine.engine import GameEngine
from engine.input import ButtonData, InputEvents
from engine.state import EffectControls, SceneControls
from engine.timer import Timer
from packs.rules.return_to_lobby.return_to_lobby_rule import ReturnToLobbyRule
from packs.tests.settings_helper import settings_for

_TICK = 0.25


class _FixedTimer(Timer):
    """Advances by exactly ``_TICK`` per update."""

    def update(self) -> None:
        self.elapsed = _TICK
        self.total += _TICK


class _RecordingSceneControls(SceneControls):
    def __init__(self) -> None:
        self.reboots_to_previous = 0

    def reboot_to_previous(self) -> None:
        self.reboots_to_previous += 1


def _hold_both(hold_seconds: float, seconds: float) -> int:
    """Hold A and B for *seconds* under a *hold_seconds* Setting; return reboots requested."""
    timer = _FixedTimer()
    engine = GameEngine(EffectControls(), timer=timer)
    engine.add_rules(ReturnToLobbyRule())
    scene_controls = _RecordingSceneControls()
    settings = settings_for(rule_packs={"return_to_lobby": {"hold_seconds": hold_seconds}})
    state = engine.create_state(scene_controls, settings=settings)
    both = ButtonData(states={"A": ButtonData.DOWN, "B": ButtonData.DOWN})
    for _ in range(round(seconds / _TICK)):
        timer.update()
        state.queue_event(InputEvents.Sensors(both))
        engine.update(state)
    return scene_controls.reboots_to_previous


def test_holding_both_buttons_for_hold_seconds_reboots_to_the_previous_scene() -> None:
    assert _hold_both(hold_seconds=1.0, seconds=1.0) == 1


def test_holding_both_buttons_short_of_hold_seconds_does_not_reboot() -> None:
    assert _hold_both(hold_seconds=1.0, seconds=0.75) == 0
