import pytest

from engine.state import EffectReceipt
from hardware.shared.voice_pool import VoicePool, VoiceSink

# ---------------------------------------------------------------------------
# Test double — a recording VoiceSink fake
# ---------------------------------------------------------------------------


class RecordingSink(VoiceSink):
    """A VoiceSink fake that records every call and tracks per-slot playing state.

    No audio hardware: ``open_source`` returns a stand-in source object (or a
    pre-configured failure), ``play`` marks the slot playing, ``stop`` marks it
    not playing, and ``is_playing`` reports that flag.  Every call is recorded
    so tests assert against observable behaviour rather than pool internals.
    """

    def __init__(self, num_voices: int) -> None:
        self.calls: list = []
        self.playing = [False] * num_voices
        # Sources returned by open_source, in order.  None entries simulate a
        # failed load.  When exhausted, a fresh unique object is returned.
        self._open_results: list = []
        self._next_source_id = 0

    def fail_next_open(self) -> None:
        """Make the next ``open_source`` call return None (a failed load)."""
        self._open_results.append(None)

    def open_source(self, path):
        self.calls.append(("open_source", path))
        if self._open_results:
            return self._open_results.pop(0)
        self._next_source_id += 1
        return ("source", self._next_source_id)

    def play(self, slot, source, loop) -> None:
        self.calls.append(("play", slot, source, loop))
        self.playing[slot] = True

    def stop(self, slot) -> None:
        self.calls.append(("stop", slot))
        self.playing[slot] = False

    def set_loudness(self, slot, loudness) -> None:
        self.calls.append(("set_loudness", slot, loudness))

    def is_playing(self, slot) -> bool:
        return self.playing[slot]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_NEXT_ID = [0]


def make_receipt(loudness: float = 1.0) -> EffectReceipt:
    _NEXT_ID[0] += 1
    receipt = EffectReceipt(_NEXT_ID[0])
    receipt.loudness = loudness
    return receipt


def play_calls(sink: RecordingSink) -> list:
    return [c for c in sink.calls if c[0] == "play"]


def stop_slots(sink: RecordingSink) -> list:
    return [c[1] for c in sink.calls if c[0] == "stop"]


@pytest.fixture()
def sink() -> RecordingSink:
    return RecordingSink(num_voices=3)


@pytest.fixture()
def pool() -> VoicePool:
    return VoicePool(num_voices=3)


# ---------------------------------------------------------------------------
# claim — basic playback into an idle slot
# ---------------------------------------------------------------------------


def test_claim_plays_into_first_idle_slot(pool: VoicePool, sink: RecordingSink) -> None:
    receipt = make_receipt()
    slot = pool.claim(sink, "clip.wav", loop=False, stops_receipt=True, receipt=receipt)
    assert slot == 0
    assert ("open_source", "clip.wav") in sink.calls
    assert play_calls(sink) == [("play", 0, ("source", 1), False)]


def test_claim_forwards_receipt_loudness_to_sink(pool: VoicePool, sink: RecordingSink) -> None:
    receipt = make_receipt(loudness=0.4)
    pool.claim(sink, "clip.wav", loop=False, stops_receipt=True, receipt=receipt)
    assert ("set_loudness", 0, 0.4) in sink.calls


def test_claim_fills_idle_slots_in_order(pool: VoicePool, sink: RecordingSink) -> None:
    slots = [
        pool.claim(sink, "a.wav", loop=False, stops_receipt=True, receipt=make_receipt())
        for _ in range(3)
    ]
    assert slots == [0, 1, 2]


def test_claim_returns_minus_one_and_opens_nothing_when_all_loops_and_new_one_shot(
    pool: VoicePool, sink: RecordingSink
) -> None:
    for _ in range(3):
        pool.claim(sink, "loop.wav", loop=True, stops_receipt=True, receipt=make_receipt())
    sink.calls.clear()
    slot = pool.claim(sink, "shot.wav", loop=False, stops_receipt=True, receipt=make_receipt())
    assert slot == -1
    assert sink.calls == []  # nothing opened, nothing torn down


# ---------------------------------------------------------------------------
# claim — failed load evicts nothing
# ---------------------------------------------------------------------------


def test_failed_load_into_idle_slot_returns_minus_one_without_playing(
    pool: VoicePool, sink: RecordingSink
) -> None:
    sink.fail_next_open()
    slot = pool.claim(sink, "missing.wav", loop=False, stops_receipt=True, receipt=make_receipt())
    assert slot == -1
    assert play_calls(sink) == []


def test_failed_load_does_not_evict_a_live_voice(pool: VoicePool, sink: RecordingSink) -> None:
    for _ in range(3):
        pool.claim(sink, "loop.wav", loop=True, stops_receipt=True, receipt=make_receipt())
    sink.calls.clear()
    sink.fail_next_open()
    slot = pool.claim(sink, "new.wav", loop=True, stops_receipt=True, receipt=make_receipt())
    assert slot == -1
    assert stop_slots(sink) == []  # no teardown of any existing voice
    # All three originals still playing — a fresh one-shot claim finds no idle slot
    sink.calls.clear()
    dropped = pool.claim(sink, "shot.wav", loop=False, stops_receipt=True, receipt=make_receipt())
    assert dropped == -1


# ---------------------------------------------------------------------------
# claim — eviction policy
# ---------------------------------------------------------------------------


def test_new_loop_evicts_oldest_loop(pool: VoicePool, sink: RecordingSink) -> None:
    # Fill with loops in slots 0,1,2 (claim order makes slot 0 oldest)
    for _ in range(3):
        pool.claim(sink, "loop.wav", loop=True, stops_receipt=True, receipt=make_receipt())
    sink.calls.clear()
    slot = pool.claim(sink, "new.wav", loop=True, stops_receipt=True, receipt=make_receipt())
    assert slot == 0
    assert ("stop", 0) in sink.calls


def test_new_loop_evicts_oldest_slot_overall_when_no_loops_present(
    pool: VoicePool, sink: RecordingSink
) -> None:
    for _ in range(3):
        pool.claim(sink, "shot.wav", loop=False, stops_receipt=True, receipt=make_receipt())
    sink.calls.clear()
    slot = pool.claim(sink, "loop.wav", loop=True, stops_receipt=True, receipt=make_receipt())
    assert slot == 0  # oldest one-shot, used as fallback


def test_new_loop_evicts_oldest_loop_not_an_older_one_shot(
    pool: VoicePool, sink: RecordingSink
) -> None:
    # slot 0 = older one-shot, slot 1 = newer loop, slot 2 = one-shot
    pool.claim(sink, "shot0.wav", loop=False, stops_receipt=True, receipt=make_receipt())
    pool.claim(sink, "loop1.wav", loop=True, stops_receipt=True, receipt=make_receipt())
    pool.claim(sink, "shot2.wav", loop=False, stops_receipt=True, receipt=make_receipt())
    sink.calls.clear()
    slot = pool.claim(sink, "new.wav", loop=True, stops_receipt=True, receipt=make_receipt())
    assert slot == 1  # the only loop, evicted even though slot 0 is older
    assert ("stop", 1) in sink.calls


def test_new_one_shot_evicts_oldest_one_shot(pool: VoicePool, sink: RecordingSink) -> None:
    # slot 0 loop, slots 1 and 2 one-shots (slot 1 older)
    pool.claim(sink, "loop.wav", loop=True, stops_receipt=True, receipt=make_receipt())
    pool.claim(sink, "s1.wav", loop=False, stops_receipt=True, receipt=make_receipt())
    pool.claim(sink, "s2.wav", loop=False, stops_receipt=True, receipt=make_receipt())
    sink.calls.clear()
    slot = pool.claim(sink, "new.wav", loop=False, stops_receipt=True, receipt=make_receipt())
    assert slot == 1  # oldest one-shot, loop in slot 0 untouched
    assert ("stop", 1) in sink.calls


def test_new_one_shot_never_evicts_a_loop(pool: VoicePool, sink: RecordingSink) -> None:
    for _ in range(3):
        pool.claim(sink, "loop.wav", loop=True, stops_receipt=True, receipt=make_receipt())
    slot = pool.claim(sink, "shot.wav", loop=False, stops_receipt=True, receipt=make_receipt())
    assert slot == -1


# ---------------------------------------------------------------------------
# claim — stops_receipt receipt-stop on eviction
# ---------------------------------------------------------------------------


def test_evicting_stops_receipt_slot_stops_its_receipt(
    pool: VoicePool, sink: RecordingSink
) -> None:
    evicted = make_receipt()
    pool.claim(sink, "a.wav", loop=True, stops_receipt=True, receipt=evicted)
    pool.claim(sink, "b.wav", loop=True, stops_receipt=True, receipt=make_receipt())
    pool.claim(sink, "c.wav", loop=True, stops_receipt=True, receipt=make_receipt())
    pool.claim(sink, "new.wav", loop=True, stops_receipt=True, receipt=make_receipt())
    assert evicted.is_stopped()


def test_evicting_slot_without_stops_receipt_leaves_receipt_to_rules(
    pool: VoicePool, sink: RecordingSink
) -> None:
    evicted = make_receipt()
    pool.claim(sink, "a.wav", loop=True, stops_receipt=False, receipt=evicted)
    pool.claim(sink, "b.wav", loop=True, stops_receipt=True, receipt=make_receipt())
    pool.claim(sink, "c.wav", loop=True, stops_receipt=True, receipt=make_receipt())
    pool.claim(sink, "new.wav", loop=True, stops_receipt=True, receipt=make_receipt())
    assert not evicted.is_stopped()


# ---------------------------------------------------------------------------
# claim — slot reuse after eviction (behavioural "freed")
# ---------------------------------------------------------------------------


def test_evicted_slot_is_reused_by_the_new_clip(pool: VoicePool, sink: RecordingSink) -> None:
    for _ in range(3):
        pool.claim(sink, "loop.wav", loop=True, stops_receipt=True, receipt=make_receipt())
    slot = pool.claim(sink, "new.wav", loop=True, stops_receipt=True, receipt=make_receipt())
    last_play = play_calls(sink)[-1]
    first_play = play_calls(sink)[0]
    assert last_play[1] == slot  # plays into the evicted slot
    assert last_play[2] != first_play[2]  # the new clip's source, not the evicted one


# ---------------------------------------------------------------------------
# sweep — natural one-shot finish
# ---------------------------------------------------------------------------


def test_sweep_frees_naturally_finished_one_shot(pool: VoicePool, sink: RecordingSink) -> None:
    pool.claim(sink, "shot.wav", loop=False, stops_receipt=False, receipt=make_receipt())
    sink.playing[0] = False  # clip ran to its end
    sink.calls.clear()
    pool.sweep(sink)
    assert ("stop", 0) in sink.calls
    # Slot is free: next claim reuses slot 0
    next_slot = pool.claim(
        sink, "next.wav", loop=False, stops_receipt=False, receipt=make_receipt()
    )
    assert next_slot == 0


def test_sweep_stops_receipt_when_stops_receipt_flag_is_set_on_natural_finish(
    pool: VoicePool, sink: RecordingSink
) -> None:
    receipt = make_receipt()
    pool.claim(sink, "shot.wav", loop=False, stops_receipt=True, receipt=receipt)
    sink.playing[0] = False
    pool.sweep(sink)
    assert receipt.is_stopped()


def test_sweep_leaves_receipt_to_rules_when_stops_receipt_flag_is_not_set(
    pool: VoicePool, sink: RecordingSink
) -> None:
    receipt = make_receipt()
    pool.claim(sink, "shot.wav", loop=False, stops_receipt=False, receipt=receipt)
    sink.playing[0] = False
    pool.sweep(sink)
    assert not receipt.is_stopped()


def test_sweep_does_not_free_a_still_playing_one_shot(pool: VoicePool, sink: RecordingSink) -> None:
    pool.claim(sink, "shot.wav", loop=False, stops_receipt=True, receipt=make_receipt())
    sink.calls.clear()
    pool.sweep(sink)  # still playing
    assert stop_slots(sink) == []
    # Slot still occupied: a new one-shot claim takes a different slot
    other = pool.claim(sink, "b.wav", loop=False, stops_receipt=True, receipt=make_receipt())
    assert other == 1


def test_sweep_does_not_free_a_finished_loop(pool: VoicePool, sink: RecordingSink) -> None:
    # A loop reports not playing only transiently; sweep must not treat it as finished
    pool.claim(sink, "loop.wav", loop=True, stops_receipt=True, receipt=make_receipt())
    sink.playing[0] = False
    sink.calls.clear()
    pool.sweep(sink)
    assert stop_slots(sink) == []


# ---------------------------------------------------------------------------
# sweep — externally-stopped receipt
# ---------------------------------------------------------------------------


def test_sweep_frees_externally_stopped_receipt(pool: VoicePool, sink: RecordingSink) -> None:
    receipt = make_receipt()
    pool.claim(sink, "loop.wav", loop=True, stops_receipt=True, receipt=receipt)
    receipt.stop()
    sink.calls.clear()
    pool.sweep(sink)
    assert ("stop", 0) in sink.calls
    next_slot = pool.claim(sink, "next.wav", loop=True, stops_receipt=True, receipt=make_receipt())
    assert next_slot == 0


def test_sweep_does_not_stop_an_already_externally_stopped_receipt_again(
    pool: VoicePool, sink: RecordingSink
) -> None:
    # An externally stopped receipt must not be re-stopped by sweep.
    class CountingReceipt(EffectReceipt):
        def __init__(self) -> None:
            super().__init__(99)
            self.stop_count = 0

        def stop(self) -> None:
            self.stop_count += 1
            super().stop()

    receipt = CountingReceipt()
    pool.claim(sink, "loop.wav", loop=True, stops_receipt=True, receipt=receipt)
    receipt.stop()  # rules stop it (count -> 1)
    pool.sweep(sink)
    assert receipt.stop_count == 1  # sweep did not stop it a second time


# ---------------------------------------------------------------------------
# sweep — loudness change
# ---------------------------------------------------------------------------


def test_sweep_reapplies_changed_loudness(pool: VoicePool, sink: RecordingSink) -> None:
    receipt = make_receipt(loudness=1.0)
    pool.claim(sink, "loop.wav", loop=True, stops_receipt=True, receipt=receipt)
    receipt.loudness = 0.25
    sink.calls.clear()
    pool.sweep(sink)
    assert sink.calls == [("set_loudness", 0, 0.25)]


def test_sweep_does_not_reapply_unchanged_loudness(pool: VoicePool, sink: RecordingSink) -> None:
    receipt = make_receipt(loudness=0.5)
    pool.claim(sink, "loop.wav", loop=True, stops_receipt=True, receipt=receipt)
    sink.calls.clear()
    pool.sweep(sink)
    assert sink.calls == []


def test_sweep_ignores_idle_slots(pool: VoicePool, sink: RecordingSink) -> None:
    pool.sweep(sink)
    assert sink.calls == []


# ---------------------------------------------------------------------------
# VoiceSink — abstract port
# ---------------------------------------------------------------------------


def test_voice_sink_methods_raise_not_implemented() -> None:
    sink = VoiceSink()
    with pytest.raises(NotImplementedError):
        sink.open_source("x")
    with pytest.raises(NotImplementedError):
        sink.play(0, object(), False)
    with pytest.raises(NotImplementedError):
        sink.stop(0)
    with pytest.raises(NotImplementedError):
        sink.set_loudness(0, 1.0)
    with pytest.raises(NotImplementedError):
        sink.is_playing(0)
