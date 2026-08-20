"""Tests for Drv2605EffectOutput — HapticPattern-based haptic sequence playback."""

from __future__ import annotations

import adafruit_drv2605  # type: ignore[import]
import pytest

from effects.effect import Effect, EffectHaptic, HapticPattern
from engine.events import EffectEvent
from engine.state import EffectReceipt, Scope
from hardware.circuitpython.drv2605_output import Drv2605EffectOutput

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SEQ_LEN = 8


class StubDriver:
    """Minimal adafruit_drv2605.DRV2605 stand-in."""

    def __init__(self) -> None:
        self.sequence: list = [adafruit_drv2605.Effect(0)] * _SEQ_LEN
        self.play_calls: int = 0
        self.stop_calls: int = 0

    def play(self) -> None:
        self.play_calls += 1

    def stop(self) -> None:
        self.stop_calls += 1


def _make_receipt() -> EffectReceipt:
    r = EffectReceipt(1)
    return r


def _make_output() -> tuple[Drv2605EffectOutput, StubDriver]:
    driver = StubDriver()
    output = Drv2605EffectOutput(driver=driver)
    return output, driver


def _effect_with_sequence(verb: str, sequence: list[int]) -> Effect:
    return Effect(
        name="test",
        haptic=EffectHaptic(patterns={verb: HapticPattern(sequence=sequence)}),
    )


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------


def test_construction_sets_min_resolution_to_one() -> None:
    """Drv2605EffectOutput exposes min_resolution = 1 so it is compatible with all effects."""
    output, _ = _make_output()

    assert output.min_resolution == 1


def test_construction_sets_scopes_to_all() -> None:
    """Drv2605EffectOutput registers on Scope.ALL so it receives every game event."""
    output, _ = _make_output()

    assert output.scopes == [Scope.ALL]


# ---------------------------------------------------------------------------
# handle_event — correct sequence written and driver plays
# ---------------------------------------------------------------------------


def test_known_verb_writes_effect_to_driver_sequence() -> None:
    output, driver = _make_output()
    effect = _effect_with_sequence(
        "strike",
        [HapticPattern.STRONG_CLICK, HapticPattern.SHARP_CLICK, HapticPattern.SOFT_BUMP],
    )
    receipt = _make_receipt()

    output.handle_event(
        EffectEvent("rlgl", "haptic", "strike"), frozenset({"all"}), effect, receipt
    )

    assert driver.sequence[0] == adafruit_drv2605.Effect(1)
    assert driver.sequence[1] == adafruit_drv2605.Effect(4)
    assert driver.sequence[2] == adafruit_drv2605.Effect(7)


def test_pause_constant_writes_pause_object_to_correct_slot() -> None:
    output, driver = _make_output()
    effect = _effect_with_sequence("strike", [HapticPattern.PAUSE_250])
    receipt = _make_receipt()

    output.handle_event(
        EffectEvent("rlgl", "haptic", "strike"), frozenset({"all"}), effect, receipt
    )

    assert driver.sequence[0] == adafruit_drv2605.Pause(0.25)


def test_all_pause_constants_write_correct_durations() -> None:
    output, driver = _make_output()
    effect = _effect_with_sequence(
        "strike",
        [HapticPattern.PAUSE_250, HapticPattern.PAUSE_500, HapticPattern.PAUSE_1000],
    )
    receipt = _make_receipt()

    output.handle_event(
        EffectEvent("rlgl", "haptic", "strike"), frozenset({"all"}), effect, receipt
    )

    assert driver.sequence[0] == adafruit_drv2605.Pause(0.25)
    assert driver.sequence[1] == adafruit_drv2605.Pause(0.5)
    assert driver.sequence[2] == adafruit_drv2605.Pause(1.0)


def test_known_verb_calls_driver_play() -> None:
    output, driver = _make_output()
    effect = _effect_with_sequence("strike", [HapticPattern.STRONG_CLICK])
    receipt = _make_receipt()

    output.handle_event(
        EffectEvent("rlgl", "haptic", "strike"), frozenset({"all"}), effect, receipt
    )

    assert driver.play_calls == 1


# ---------------------------------------------------------------------------
# handle_event — slot clearing
# ---------------------------------------------------------------------------


def test_shorter_sequence_clears_remaining_slots_to_effect_zero() -> None:
    output, driver = _make_output()
    effect = _effect_with_sequence("strike", [HapticPattern.STRONG_CLICK])
    receipt = _make_receipt()

    output.handle_event(
        EffectEvent("rlgl", "haptic", "strike"), frozenset({"all"}), effect, receipt
    )

    for i in range(1, _SEQ_LEN):
        assert driver.sequence[i] == adafruit_drv2605.Effect(0)


def test_second_event_with_shorter_sequence_clears_stale_slots() -> None:
    output, driver = _make_output()
    long_effect = _effect_with_sequence(
        "strike",
        [
            HapticPattern.STRONG_CLICK,
            HapticPattern.SHARP_CLICK,
            HapticPattern.SOFT_BUMP,
        ],
    )
    short_effect = _effect_with_sequence("strike", [HapticPattern.STRONG_BUZZ])

    output.handle_event(
        EffectEvent("rlgl", "haptic", "strike"), frozenset({"all"}), long_effect, _make_receipt()
    )
    output.handle_event(
        EffectEvent("rlgl", "haptic", "strike"), frozenset({"all"}), short_effect, _make_receipt()
    )

    assert driver.sequence[0] == adafruit_drv2605.Effect(14)
    for i in range(1, _SEQ_LEN):
        assert driver.sequence[i] == adafruit_drv2605.Effect(0)


# ---------------------------------------------------------------------------
# handle_event — interruption
# ---------------------------------------------------------------------------


def test_second_event_calls_play_again_without_stop() -> None:
    output, driver = _make_output()
    effect = _effect_with_sequence("strike", [HapticPattern.STRONG_CLICK])
    receipt1 = _make_receipt()
    receipt2 = _make_receipt()

    output.handle_event(
        EffectEvent("rlgl", "haptic", "strike"), frozenset({"all"}), effect, receipt1
    )
    output.handle_event(
        EffectEvent("rlgl", "haptic", "strike"), frozenset({"all"}), effect, receipt2
    )

    assert driver.play_calls == 2
    assert driver.stop_calls == 0


# ---------------------------------------------------------------------------
# handle_event — early-return guards
# ---------------------------------------------------------------------------


def test_handle_event_ignores_effect_with_no_haptic() -> None:
    output, driver = _make_output()
    effect = Effect(name="silent")
    receipt = _make_receipt()

    output.handle_event(
        EffectEvent("rlgl", "silent", "strike"), frozenset({"all"}), effect, receipt
    )

    assert driver.play_calls == 0


def test_handle_event_ignores_unknown_verb() -> None:
    output, driver = _make_output()
    effect = _effect_with_sequence("strike", [HapticPattern.STRONG_CLICK])
    receipt = _make_receipt()

    output.handle_event(EffectEvent("rlgl", "haptic", "stop"), frozenset({"all"}), effect, receipt)

    assert driver.play_calls == 0


# ---------------------------------------------------------------------------
# handle_event — error cases
# ---------------------------------------------------------------------------


def test_sequence_longer_than_8_raises() -> None:
    """Sequence with more than 8 steps raises ValueError — developer error."""
    output, _ = _make_output()
    effect = _effect_with_sequence(
        "strike",
        [HapticPattern.STRONG_CLICK] * 9,
    )
    receipt = _make_receipt()

    with pytest.raises(ValueError):
        output.handle_event(
            EffectEvent("rlgl", "haptic", "strike"), frozenset({"all"}), effect, receipt
        )


def test_unknown_constant_in_sequence_raises() -> None:
    """An unmapped constant in the sequence raises KeyError — developer error."""
    output, _ = _make_output()
    effect = _effect_with_sequence("strike", [999])
    receipt = _make_receipt()

    with pytest.raises(KeyError):
        output.handle_event(
            EffectEvent("rlgl", "haptic", "strike"), frozenset({"all"}), effect, receipt
        )


# ---------------------------------------------------------------------------
# flush — receipt externally stopped
# ---------------------------------------------------------------------------


def test_flush_calls_driver_stop_when_active_receipt_is_externally_stopped() -> None:
    output, driver = _make_output()
    effect = _effect_with_sequence("strike", [HapticPattern.STRONG_CLICK])
    receipt = _make_receipt()

    output.handle_event(
        EffectEvent("rlgl", "haptic", "strike"), frozenset({"all"}), effect, receipt
    )
    receipt.stop()
    output.flush()

    assert driver.stop_calls == 1


def test_flush_clears_receipt_after_stopping_driver() -> None:
    """flush() clears the active receipt so a subsequent flush() does not call stop() again."""
    output, driver = _make_output()
    effect = _effect_with_sequence("strike", [HapticPattern.STRONG_CLICK])
    receipt = _make_receipt()

    output.handle_event(
        EffectEvent("rlgl", "haptic", "strike"), frozenset({"all"}), effect, receipt
    )
    receipt.stop()
    output.flush()
    output.flush()

    assert driver.stop_calls == 1


def test_flush_does_nothing_when_no_active_receipt() -> None:
    output, driver = _make_output()

    output.flush()

    assert driver.stop_calls == 0


def test_flush_does_nothing_when_receipt_is_still_active() -> None:
    output, driver = _make_output()
    effect = _effect_with_sequence("strike", [HapticPattern.STRONG_CLICK])
    receipt = _make_receipt()

    output.handle_event(
        EffectEvent("rlgl", "haptic", "strike"), frozenset({"all"}), effect, receipt
    )
    output.flush()

    assert driver.stop_calls == 0
