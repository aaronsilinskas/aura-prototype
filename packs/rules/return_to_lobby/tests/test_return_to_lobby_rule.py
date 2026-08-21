"""Behavioral tests for ReturnToLobbyRule.

Uses a controllable stub ``Timer`` (mirrors the RLGL game-rule tests'
``_StubTimer``) so hold duration can be advanced deterministically instead of
depending on wall-clock time between event dispatches, and a local
``RecordingSceneControls`` double so a rule-level unit test can assert on
``reboot_to_previous()`` without a live ``SceneManager``.
"""

from __future__ import annotations

from engine.engine import GameEngine
from engine.input import ButtonData, InputEvents
from engine.state import EffectControls, GameState, SceneControls
from packs.rules.return_to_lobby.return_to_lobby_rule import ReturnToLobbyRule


class _StubTimer:
    """Controllable timer: caller sets ``elapsed`` directly before each tick."""

    def __init__(self) -> None:
        self.elapsed: float = 0.0
        self.total: float = 0.0

    def update(self) -> None:
        pass  # caller controls elapsed/total directly


class RecordingSceneControls(SceneControls):
    """Records ``reboot_to_previous`` calls instead of raising ``NotImplementedError``.

    Mirrors ``engine.tests.helpers.RecordingSceneReboot`` at the rule-facing
    ``SceneControls`` seam, since ``ReturnToLobbyRule`` calls
    ``state.scene_controls.reboot_to_previous()`` directly rather than
    through a live ``SceneManager``.
    """

    def __init__(self) -> None:
        self.reboot_to_previous_calls: int = 0

    def reboot_to_previous(self) -> None:
        self.reboot_to_previous_calls += 1


def _make_state(
    initial_data: dict | None = None,
) -> tuple[GameState, GameEngine, _StubTimer, RecordingSceneControls]:
    timer = _StubTimer()
    engine = GameEngine(EffectControls(), timer=timer)  # pyright: ignore[reportArgumentType]
    engine.add_rules(ReturnToLobbyRule())
    scene_controls = RecordingSceneControls()
    state = engine.create_state(scene_controls, initial_data=initial_data or {})
    return state, engine, timer, scene_controls


def _tick(
    state: GameState,
    engine: GameEngine,
    timer: _StubTimer,
    elapsed: float,
    button_a: bool = False,
    button_b: bool = False,
) -> None:
    """Advance the stub timer by *elapsed* seconds and dispatch one Sensors event."""
    timer.elapsed = elapsed
    timer.total += elapsed
    button_states: dict[str, int] = {}
    if button_a:
        button_states["A"] = ButtonData.DOWN
    if button_b:
        button_states["B"] = ButtonData.DOWN
    state.queue_event(InputEvents.Sensors(ButtonData(states=button_states)))
    engine.update(state)


def test_reaching_default_hold_seconds_threshold_calls_reboot_to_previous() -> None:
    state, engine, timer, scene_controls = _make_state()

    _tick(state, engine, timer, elapsed=3.0, button_a=True, button_b=True)
    _tick(state, engine, timer, elapsed=2.0, button_a=True, button_b=True)

    assert scene_controls.reboot_to_previous_calls == 1


def test_partial_hold_below_threshold_does_not_reboot() -> None:
    state, engine, timer, scene_controls = _make_state()

    _tick(state, engine, timer, elapsed=3.0, button_a=True, button_b=True)
    _tick(state, engine, timer, elapsed=1.9, button_a=True, button_b=True)

    assert scene_controls.reboot_to_previous_calls == 0


def test_releasing_b_resets_the_accumulator_so_a_later_partial_hold_does_not_reboot() -> None:
    state, engine, timer, scene_controls = _make_state()

    _tick(state, engine, timer, elapsed=4.0, button_a=True, button_b=True)
    _tick(state, engine, timer, elapsed=0.1, button_a=True, button_b=False)  # B released
    _tick(state, engine, timer, elapsed=4.9, button_a=True, button_b=True)

    assert scene_controls.reboot_to_previous_calls == 0


def test_full_hold_after_a_release_still_reaches_threshold_and_reboots() -> None:
    state, engine, timer, scene_controls = _make_state()

    _tick(state, engine, timer, elapsed=4.0, button_a=True, button_b=True)
    _tick(state, engine, timer, elapsed=0.1, button_a=False, button_b=True)  # A released
    _tick(state, engine, timer, elapsed=5.0, button_a=True, button_b=True)

    assert scene_controls.reboot_to_previous_calls == 1


def test_hold_seconds_is_configurable_via_initial_data() -> None:
    state, engine, timer, scene_controls = _make_state(
        initial_data={"return_to_lobby": {"hold_seconds": 1.0}}
    )

    _tick(state, engine, timer, elapsed=1.0, button_a=True, button_b=True)

    assert scene_controls.reboot_to_previous_calls == 1


def test_configured_hold_seconds_below_threshold_does_not_reboot() -> None:
    state, engine, timer, scene_controls = _make_state(
        initial_data={"return_to_lobby": {"hold_seconds": 1.0}}
    )

    _tick(state, engine, timer, elapsed=0.9, button_a=True, button_b=True)

    assert scene_controls.reboot_to_previous_calls == 0
