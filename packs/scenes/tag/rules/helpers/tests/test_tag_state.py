"""Tests for ``TagState`` — phase transitions, the entered flag, and the
``tag_state`` get-or-create accessor."""

from __future__ import annotations

from engine.engine import GameEngine
from engine.state import SceneControls
from engine.tests.helpers import SpyEffectControls
from packs.scenes.tag.rules.helpers.phases import PHASE_PLAYING, PHASE_READY
from packs.scenes.tag.rules.helpers.tag_state import TagState, tag_state


class _StubTimer:
    def __init__(self) -> None:
        self.elapsed: float = 0.0
        self.total: float = 0.0

    def update(self) -> None:
        pass


def _make_state(initial_data: dict | None = None):
    spy = SpyEffectControls()
    timer = _StubTimer()
    engine = GameEngine(spy, timer=timer)  # pyright: ignore[reportArgumentType]
    return engine.create_state(SceneControls(), initial_data=initial_data or {})


# ---------------------------------------------------------------------------
# Construction defaults
# ---------------------------------------------------------------------------


def test_new_tag_state_starts_in_ready_phase_not_yet_entered():
    tag = TagState()

    assert tag.phase == PHASE_READY
    assert tag.just_entered is True


def test_new_tag_state_has_no_receipts():
    tag = TagState()

    assert tag.progress_receipt is None
    assert tag.warning_receipt is None
    assert tag.game_over_receipt is None


# ---------------------------------------------------------------------------
# enter — atomic phase transition + entered reset
# ---------------------------------------------------------------------------


def test_enter_sets_the_new_phase():
    tag = TagState()
    tag.mark_entered()

    tag.enter(PHASE_PLAYING)

    assert tag.phase == PHASE_PLAYING


def test_enter_resets_just_entered_to_true():
    tag = TagState()
    tag.mark_entered()
    assert tag.just_entered is False

    tag.enter(PHASE_PLAYING)

    assert tag.just_entered is True


def test_mark_entered_clears_just_entered():
    tag = TagState()

    tag.mark_entered()

    assert tag.just_entered is False


# ---------------------------------------------------------------------------
# tag_state — get-or-create accessor
# ---------------------------------------------------------------------------


def test_tag_state_caches_the_same_instance_across_calls():
    state = _make_state()

    first = tag_state(state)
    second = tag_state(state)

    assert first is second


def test_tag_state_mutations_persist_across_accessor_calls():
    state = _make_state()

    tag_state(state).hitpoints = 7

    assert tag_state(state).hitpoints == 7
