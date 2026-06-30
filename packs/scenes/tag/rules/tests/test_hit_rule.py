"""Tests for TagHitRule — receive, identity gate, deafen gate, and damage."""

from __future__ import annotations

import pytest

from engine.engine import GameEngine
from engine.network import NetworkEvents
from engine.state import GameState, SceneControls, Scope
from engine.tests.helpers import SpyEffectControls
from hardware.shared.tag_protocol import TagData, encode_tag_data
from packs.scenes.tag.rules.helpers.phases import PHASE_PLAYING, PHASE_READY
from packs.scenes.tag.rules.helpers.tag_state import tag_state
from packs.scenes.tag.rules.hit_rule import TagHitRule
from packs.scenes.tag.rules.tests.helpers import StubTimer, seed_phase


@pytest.fixture()
def spy() -> SpyEffectControls:
    return SpyEffectControls()


def _make_state(
    spy: SpyEffectControls, initial_data: dict | None = None
) -> tuple[GameState, GameEngine, StubTimer]:
    timer = StubTimer()
    engine = GameEngine(spy, timer=timer)  # pyright: ignore
    engine.add_rules(TagHitRule())
    state = engine.create_state(SceneControls(), initial_data=initial_data or {})
    tag = seed_phase(state, PHASE_PLAYING, entered=True)
    tag.hitpoints = 10
    return state, engine, timer


def _receive(
    state: GameState,
    engine: GameEngine,
    timer: StubTimer,
    total: float,
    tag_data: TagData,
    signal_strength: float | None = 1.0,
    error_margin: int | None = 0,
) -> None:
    timer.total = total
    payload = bytes(encode_tag_data(tag_data))
    state.queue_event(NetworkEvents.IRReceived(payload, signal_strength, error_margin, "front"))
    engine.update(state)


def test_matching_hit_plays_hit_effect_on_global_main(spy):
    state, engine, timer = _make_state(spy)

    _receive(state, engine, timer, 1.0, TagData(team=0, player=1, damage=1))

    hit_calls = [c for c in spy.set_effect_calls if c[1] == "scene.hit"]
    assert len(hit_calls) == 1
    scope, _, _ = hit_calls[0]
    assert scope is Scope.Global.MAIN


def test_matching_hit_reduces_hitpoints_and_reissues_progress_bar(spy):
    state, engine, timer = _make_state(spy)

    _receive(state, engine, timer, 1.0, TagData(team=0, player=1, damage=1))

    assert tag_state(state).hitpoints == 10 - 1
    progress_calls = [c for c in spy.set_effect_calls if c[1] == "basic.progress"]
    assert len(progress_calls) == 1
    scope, _, options = progress_calls[0]
    assert scope is Scope.PERSONAL
    expected_fraction = (10 - 1) / 10
    assert options == {"progress": pytest.approx(expected_fraction), "color": 0x00FF00}


def test_matching_hit_stores_hitpoints_receipt(spy):
    state, engine, timer = _make_state(spy)

    _receive(state, engine, timer, 1.0, TagData(team=0, player=1, damage=1))

    assert tag_state(state).hitpoints_receipt is not None


def test_hit_during_reload_subtracts_hitpoints_without_interrupting_reload(spy):
    state, engine, timer = _make_state(spy)
    tag = tag_state(state)
    tag.shot.reload_started_at = 0.5

    _receive(state, engine, timer, 1.0, TagData(team=0, player=1, damage=1))

    assert tag_state(state).hitpoints == 10 - 1
    assert tag_state(state).shot.reload_started_at == pytest.approx(0.5)


def test_hit_with_higher_damage_reduces_hitpoints_by_that_amount(spy):
    state, engine, timer = _make_state(spy)

    _receive(state, engine, timer, 1.0, TagData(team=0, player=1, damage=4))

    assert tag_state(state).hitpoints == 10 - 4


def test_identity_mismatch_does_not_change_hitpoints(spy, capsys):
    state, engine, timer = _make_state(spy)

    _receive(state, engine, timer, 1.0, TagData(team=1, player=2, damage=1))

    assert tag_state(state).hitpoints == 10
    assert spy.set_effect_calls == []
    out = capsys.readouterr().out
    assert "ignored" in out
    assert "team=1" in out
    assert "player=2" in out


def test_within_deafen_window_does_not_change_hitpoints(spy, capsys):
    state, engine, timer = _make_state(spy)
    tag_state(state).deafen_until = 1.0

    _receive(state, engine, timer, 0.5, TagData(team=0, player=1, damage=1))

    assert tag_state(state).hitpoints == 10
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
    seed_phase(state, PHASE_READY, entered=True)

    _receive(state, engine, timer, 1.0, TagData(team=0, player=1, damage=1))

    assert tag_state(state).hitpoints == 10
    assert spy.set_effect_calls == []
