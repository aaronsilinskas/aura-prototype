"""Tests for TagHitRule — receive, identity gate, deafen gate, and damage."""

from __future__ import annotations

import pytest

from engine.engine import GameEngine
from engine.network import NetworkEvents
from engine.state import GameState, SceneControls, Scope
from engine.tests.helpers import SpyEffectControls
from hardware.shared.tag_protocol import TagData, encode_tag_data
from packs.scenes.tag.rules.helpers.phases import (
    DEFAULT_STARTING_HITPOINTS,
    KEY_DEAFEN_UNTIL,
    KEY_HITPOINTS,
    KEY_PHASE,
    PHASE_PLAYING,
)
from packs.scenes.tag.rules.hit_rule import TagHitRule


class _StubTimer:
    """Controllable timer for tests that need specific total values."""

    def __init__(self) -> None:
        self.elapsed: float = 0.0
        self.total: float = 0.0

    def update(self) -> None:
        pass  # Caller controls total directly


@pytest.fixture()
def spy() -> SpyEffectControls:
    return SpyEffectControls()


def _make_state(
    spy: SpyEffectControls, initial_data: dict | None = None
) -> tuple[GameState, GameEngine, _StubTimer]:
    timer = _StubTimer()
    engine = GameEngine(spy, timer=timer)  # pyright: ignore
    engine.add_rules(TagHitRule())
    data = {
        "tag_phase": PHASE_PLAYING,
        KEY_HITPOINTS: DEFAULT_STARTING_HITPOINTS,
    }
    if initial_data:
        data.update(initial_data)
    state = engine.create_state(SceneControls(), initial_data=data)
    return state, engine, timer


def _receive(
    state: GameState,
    engine: GameEngine,
    timer: _StubTimer,
    total: float,
    tag_data: TagData,
    signal_strength: float | None = 1.0,
    error_margin: int | None = 0,
) -> None:
    timer.total = total
    payload = bytes(encode_tag_data(tag_data))
    state.queue_event(NetworkEvents.IRReceived(payload, signal_strength, error_margin, "front"))
    engine.update(state)


def test_matching_hit_reduces_hitpoints_and_reissues_progress_bar(spy):
    state, engine, timer = _make_state(spy)

    _receive(state, engine, timer, 1.0, TagData(team=0, player=1, damage=1))

    assert state.get(KEY_HITPOINTS, None) == DEFAULT_STARTING_HITPOINTS - 1
    progress_calls = [c for c in spy.set_effect_calls if c[1] == "basic.progress"]
    assert len(progress_calls) == 1
    scope, _, options = progress_calls[0]
    assert scope is Scope.PERSONAL
    expected_fraction = (DEFAULT_STARTING_HITPOINTS - 1) / DEFAULT_STARTING_HITPOINTS
    assert options == {"progress": pytest.approx(expected_fraction)}


def test_hit_with_higher_damage_reduces_hitpoints_by_that_amount(spy):
    state, engine, timer = _make_state(spy)

    _receive(state, engine, timer, 1.0, TagData(team=0, player=1, damage=4))

    assert state.get(KEY_HITPOINTS, None) == DEFAULT_STARTING_HITPOINTS - 4


def test_identity_mismatch_does_not_change_hitpoints(spy, capsys):
    state, engine, timer = _make_state(spy)

    _receive(state, engine, timer, 1.0, TagData(team=1, player=2, damage=1))

    assert state.get(KEY_HITPOINTS, None) == DEFAULT_STARTING_HITPOINTS
    assert spy.set_effect_calls == []
    out = capsys.readouterr().out
    assert "ignored" in out
    assert "team=1" in out
    assert "player=2" in out


def test_within_deafen_window_does_not_change_hitpoints(spy, capsys):
    state, engine, timer = _make_state(spy, initial_data={KEY_DEAFEN_UNTIL: 1.0})

    _receive(state, engine, timer, 0.5, TagData(team=0, player=1, damage=1))

    assert state.get(KEY_HITPOINTS, None) == DEFAULT_STARTING_HITPOINTS
    assert spy.set_effect_calls == []
    assert "deafened" in capsys.readouterr().out


def test_counted_hit_logs_tag_data_signal_strength_and_error_margin(spy, capsys):
    state, engine, timer = _make_state(spy)

    _receive(
        state,
        engine,
        timer,
        1.0,
        TagData(team=0, player=1, damage=2),
        signal_strength=0.75,
        error_margin=42,
    )

    out = capsys.readouterr().out
    assert "team=0" in out
    assert "player=1" in out
    assert "damage=2" in out
    assert "0.75" in out
    assert "42" in out


def test_non_playing_phase_is_ignored(spy):
    state, engine, timer = _make_state(spy)
    state.set(KEY_PHASE, "ready")

    _receive(state, engine, timer, 1.0, TagData(team=0, player=1, damage=1))

    assert state.get(KEY_HITPOINTS, None) == DEFAULT_STARTING_HITPOINTS
    assert spy.set_effect_calls == []
