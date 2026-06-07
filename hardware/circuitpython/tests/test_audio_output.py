"""Tests for AudioEffectOutput — flat N-voice pool with idle-first selection."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from effects.effect import AudioPlaybackConfig, Effect, EffectAudio
from engine.audio import AudioRegistry
from engine.events import EffectEvent
from engine.state import EffectReceipt
from hardware.circuitpython.audio_output import AudioEffectOutput

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_receipt(loudness: float = 1.0) -> MagicMock:
    r = MagicMock(spec=EffectReceipt)
    r.is_stopped.return_value = False
    r.loudness = loudness
    return r


def _make_output(
    audio_registry: AudioRegistry, max_volume: float = 0.2, num_voices: int = 2
) -> AudioEffectOutput:
    """Build an AudioEffectOutput with all hardware deps patched out."""
    import audiobusio  # type: ignore[import]
    import audiocore  # type: ignore[import]
    import audiomixer  # type: ignore[import]

    audiobusio.I2SOut = MagicMock(return_value=MagicMock())
    audiocore.WaveFile = MagicMock(return_value=MagicMock())
    mock_mixer = MagicMock()
    mock_mixer.voice = [MagicMock() for _ in range(num_voices)]
    audiomixer.Mixer = MagicMock(return_value=mock_mixer)

    from hardware.circuitpython.audio_output import AudioEffectOutput

    return AudioEffectOutput(
        audio_registry=audio_registry, max_volume=max_volume, num_voices=num_voices
    )


def _effect_oneshot(verb: str, clip_name: str) -> Effect:
    return Effect(
        name="test",
        audio=EffectAudio(clips={verb: AudioPlaybackConfig(name=clip_name, loop=False)}),
    )


def _effect_loop(verb: str, clip_name: str) -> Effect:
    return Effect(
        name="test",
        audio=EffectAudio(clips={verb: AudioPlaybackConfig(name=clip_name, loop=True)}),
    )


def _fill_pool(
    output: AudioEffectOutput,
    wav: Path,
    registry: AudioRegistry,
    num_voices: int,
    *,
    loop: bool,
) -> list[MagicMock]:
    """Fill all voice slots via handle_event; returns receipts in slot order (0 = oldest)."""
    receipts = []
    for i in range(num_voices):
        clip_name = f"_fill_{'loop' if loop else 'shot'}_{i}"
        registry.register(clip_name, str(wav))
        effect = _effect_loop("start", clip_name) if loop else _effect_oneshot("start", clip_name)
        receipt = _make_receipt()
        output.handle_event(
            EffectEvent("rlgl", "fill", "start"), frozenset({"personal"}), effect, receipt
        )
        receipts.append(receipt)
    return receipts


# ---------------------------------------------------------------------------
# Constructor — required parameters
# ---------------------------------------------------------------------------


def test_requires_num_voices_and_max_volume() -> None:
    """AudioEffectOutput must be constructed with max_volume and num_voices — no defaults."""
    import audiobusio  # type: ignore[import]
    import audiomixer  # type: ignore[import]

    audiobusio.I2SOut = MagicMock(return_value=MagicMock())
    mock_mixer = MagicMock()
    mock_mixer.voice = []
    audiomixer.Mixer = MagicMock(return_value=mock_mixer)

    from hardware.circuitpython.audio_output import AudioEffectOutput

    with pytest.raises(TypeError):
        AudioEffectOutput(audio_registry=AudioRegistry())  # type: ignore[call-arg]


def test_mixer_constructed_with_num_voices() -> None:
    """audiomixer.Mixer is constructed with voice_count=num_voices."""
    import audiomixer  # type: ignore[import]

    registry = AudioRegistry()
    _make_output(registry, num_voices=4)

    audiomixer.Mixer.assert_called_once()
    call_kwargs = audiomixer.Mixer.call_args[1]
    assert call_kwargs["voice_count"] == 4


# ---------------------------------------------------------------------------
# Voice selection — idle-first, loop vs one-shot
# ---------------------------------------------------------------------------


def test_loop_clip_claims_first_idle_slot(tmp_path) -> None:
    """A loop clip claims slot 0 when all voices are idle."""
    wav = tmp_path / "music_start.wav"
    wav.write_bytes(b"RIFF")

    registry = AudioRegistry()
    registry.register("music_start", str(wav))

    output = _make_output(registry)
    effect = _effect_loop("start", "music_start")
    receipt = _make_receipt()

    output.handle_event(
        EffectEvent("rlgl", "music", "start"), frozenset({"ambient"}), effect, receipt
    )

    output._mixer.voice[0].play.assert_called()
    output._mixer.voice[1].play.assert_not_called()


def test_oneshot_clip_claims_first_idle_slot(tmp_path) -> None:
    """A one-shot clip claims slot 0 when all voices are idle."""
    wav = tmp_path / "sting_start.wav"
    wav.write_bytes(b"RIFF")

    registry = AudioRegistry()
    registry.register("sting_start", str(wav))

    output = _make_output(registry)
    effect = _effect_oneshot("start", "sting_start")
    receipt = _make_receipt()

    output.handle_event(
        EffectEvent("rlgl", "sting", "start"), frozenset({"personal"}), effect, receipt
    )

    output._mixer.voice[0].play.assert_called()
    output._mixer.voice[1].play.assert_not_called()


def test_second_clip_claims_next_idle_slot(tmp_path) -> None:
    """A second clip claims slot 1 when slot 0 is occupied."""
    wav = tmp_path / "clip.wav"
    wav.write_bytes(b"RIFF")

    registry = AudioRegistry()
    registry.register("clip_a", str(wav))
    registry.register("clip_b", str(wav))

    output = _make_output(registry)

    # Occupy slot 0 via handle_event
    output.handle_event(
        EffectEvent("rlgl", "clip", "start"),
        frozenset({"personal"}),
        _effect_oneshot("start", "clip_a"),
        _make_receipt(),
    )

    # Reset to observe only the second call
    for v in output._mixer.voice:
        v.reset_mock()

    receipt = _make_receipt()
    output.handle_event(
        EffectEvent("rlgl", "clip", "start"),
        frozenset({"personal"}),
        _effect_oneshot("start", "clip_b"),
        receipt,
    )

    output._mixer.voice[0].play.assert_not_called()
    output._mixer.voice[1].play.assert_called()


def test_oneshot_evicts_oldest_oneshot_when_all_voices_occupied(tmp_path) -> None:
    """With all voices occupied by one-shots, a new one-shot evicts the oldest slot."""
    wav = tmp_path / "clip.wav"
    wav.write_bytes(b"RIFF")

    registry = AudioRegistry()
    registry.register("new_clip", str(wav))

    output = _make_output(registry, num_voices=2)
    _fill_pool(output, wav, registry, 2, loop=False)

    for v in output._mixer.voice:
        v.reset_mock()

    effect = _effect_oneshot("start", "new_clip")
    receipt = _make_receipt()
    output.handle_event(
        EffectEvent("rlgl", "clip", "start"), frozenset({"personal"}), effect, receipt
    )

    # Slot 0 (oldest one-shot) is evicted and replayed
    output._mixer.voice[0].stop.assert_called()
    output._mixer.voice[0].play.assert_called()
    assert output._receipts[0] is receipt


# ---------------------------------------------------------------------------
# Early-return guards
# ---------------------------------------------------------------------------


def test_handle_event_ignores_effect_with_no_audio() -> None:
    """effect.audio is None → no play, no crash."""
    registry = AudioRegistry()
    output = _make_output(registry)
    effect = Effect(name="silent")
    receipt = _make_receipt()

    output.handle_event(
        EffectEvent("rlgl", "silent", "start"), frozenset({"personal"}), effect, receipt
    )

    output._mixer.voice[0].play.assert_not_called()
    output._mixer.voice[1].play.assert_not_called()


def test_handle_event_ignores_unknown_verb() -> None:
    """Verb not in clips → no play, no crash."""
    registry = AudioRegistry()
    output = _make_output(registry)
    effect = _effect_oneshot("peak", "some_peak")
    receipt = _make_receipt()

    output.handle_event(
        EffectEvent("rlgl", "effect", "stop"), frozenset({"personal"}), effect, receipt
    )

    output._mixer.voice[0].play.assert_not_called()
    output._mixer.voice[1].play.assert_not_called()


def test_handle_event_ignores_unregistered_clip() -> None:
    """Clip name not in AudioRegistry → no play, no crash."""
    registry = AudioRegistry()
    output = _make_output(registry)
    effect = _effect_oneshot("start", "missing_clip")
    receipt = _make_receipt()

    output.handle_event(
        EffectEvent("rlgl", "effect", "start"), frozenset({"personal"}), effect, receipt
    )

    output._mixer.voice[0].play.assert_not_called()
    output._mixer.voice[1].play.assert_not_called()


def test_handle_event_ignores_oserror_on_file_open(tmp_path) -> None:
    """OSError opening the WAV file → no play, no crash."""
    registry = AudioRegistry()
    registry.register("missing", str(tmp_path / "nonexistent.wav"))

    output = _make_output(registry)
    effect = _effect_oneshot("start", "missing")
    receipt = _make_receipt()

    output.handle_event(
        EffectEvent("rlgl", "effect", "start"), frozenset({"personal"}), effect, receipt
    )

    output._mixer.voice[0].play.assert_not_called()
    output._mixer.voice[1].play.assert_not_called()


# ---------------------------------------------------------------------------
# flush — natural one-shot finish frees slot
# ---------------------------------------------------------------------------


def test_flush_frees_slot_when_oneshot_finishes_naturally(tmp_path) -> None:
    """flush: voice finishes playing naturally → slot freed, receipt NOT stopped."""
    wav = tmp_path / "sting.wav"
    wav.write_bytes(b"RIFF")

    registry = AudioRegistry()
    registry.register("sting", str(wav))

    output = _make_output(registry)
    receipt = _make_receipt()
    output.handle_event(
        EffectEvent("rlgl", "sting", "start"),
        frozenset({"personal"}),
        _effect_oneshot("start", "sting"),
        receipt,
    )

    output._mixer.voice[0].playing = False
    output.flush()

    receipt.stop.assert_not_called()
    assert output._receipts[0] is None
    assert output._wave_files[0] is None
    assert output._wave_objs[0] is None


def test_flush_frees_slot_on_any_index(tmp_path) -> None:
    """flush detects natural one-shot finish on any slot index, not just slot 0."""
    wav = tmp_path / "sting.wav"
    wav.write_bytes(b"RIFF")

    registry = AudioRegistry()
    output = _make_output(registry, num_voices=3)

    # Fill all 3 slots; check that slot 2 (not slot 0) is freed
    receipts = _fill_pool(output, wav, registry, 3, loop=False)

    output._mixer.voice[2].playing = False
    output.flush()

    receipts[2].stop.assert_not_called()
    assert output._receipts[2] is None


def test_flush_does_not_free_loop_slot_when_still_playing(tmp_path) -> None:
    """flush: loop voice still playing and receipt alive → slot not freed."""
    wav = tmp_path / "music.wav"
    wav.write_bytes(b"RIFF")

    registry = AudioRegistry()
    registry.register("music", str(wav))

    output = _make_output(registry)
    receipt = _make_receipt()
    output.handle_event(
        EffectEvent("rlgl", "music", "start"),
        frozenset({"ambient"}),
        _effect_loop("start", "music"),
        receipt,
    )

    output._mixer.voice[0].playing = True
    output._mixer.voice[0].reset_mock()
    output.flush()

    assert output._receipts[0] is receipt
    output._mixer.voice[0].stop.assert_not_called()


# ---------------------------------------------------------------------------
# flush — externally-stopped receipt
# ---------------------------------------------------------------------------


def test_flush_stops_voice_and_frees_slot_when_receipt_externally_stopped(tmp_path) -> None:
    """flush: externally-stopped receipt → voice stopped, slot freed."""
    wav = tmp_path / "clip.wav"
    wav.write_bytes(b"RIFF")

    registry = AudioRegistry()
    registry.register("clip", str(wav))

    output = _make_output(registry)
    receipt = _make_receipt()
    output.handle_event(
        EffectEvent("rlgl", "clip", "start"),
        frozenset({"personal"}),
        _effect_oneshot("start", "clip"),
        receipt,
    )

    receipt.is_stopped.return_value = True
    output._mixer.voice[0].playing = True
    output._mixer.voice[0].reset_mock()
    output.flush()

    output._mixer.voice[0].stop.assert_called_once()
    assert output._receipts[0] is None
    assert output._wave_files[0] is None
    assert output._wave_objs[0] is None


def test_flush_clears_natural_finish_before_stopped_check(tmp_path) -> None:
    """flush: naturally-finished slot clears receipt before stopped check — no double processing."""
    wav = tmp_path / "clip.wav"
    wav.write_bytes(b"RIFF")

    registry = AudioRegistry()
    registry.register("clip", str(wav))

    output = _make_output(registry)
    receipt = _make_receipt()
    output.handle_event(
        EffectEvent("rlgl", "clip", "start"),
        frozenset({"personal"}),
        _effect_oneshot("start", "clip"),
        receipt,
    )

    receipt.is_stopped.return_value = True
    output._mixer.voice[0].playing = False
    output._mixer.voice[0].reset_mock()
    output.flush()

    # Natural finish cleared first, so stopped check sees receipt=None and skips
    output._mixer.voice[0].stop.assert_not_called()
    assert output._receipts[0] is None


# ---------------------------------------------------------------------------
# flush — per-slot loudness updates
# ---------------------------------------------------------------------------


def test_flush_updates_loudness_when_receipt_loudness_changes(tmp_path) -> None:
    """flush: receipt.loudness changed since last tick → voice level reapplied."""
    wav = tmp_path / "music.wav"
    wav.write_bytes(b"RIFF")

    registry = AudioRegistry()
    registry.register("music", str(wav))

    output = _make_output(registry, max_volume=0.4)
    receipt = _make_receipt(loudness=1.0)
    output.handle_event(
        EffectEvent("pack", "music", "start"),
        frozenset({"ambient"}),
        _effect_loop("start", "music"),
        receipt,
    )

    receipt.loudness = 0.5
    output._mixer.voice[0].playing = True
    output.flush()

    assert output._mixer.voice[0].level == pytest.approx(0.4 * 0.5)
    assert output._loudness[0] == 0.5


def test_flush_does_not_update_loudness_when_unchanged(tmp_path) -> None:
    """flush: receipt.loudness unchanged → voice level not reapplied."""
    wav = tmp_path / "music.wav"
    wav.write_bytes(b"RIFF")

    registry = AudioRegistry()
    registry.register("music", str(wav))

    output = _make_output(registry, max_volume=0.4)
    receipt = _make_receipt(loudness=0.75)
    output.handle_event(
        EffectEvent("pack", "music", "start"),
        frozenset({"ambient"}),
        _effect_loop("start", "music"),
        receipt,
    )

    output._mixer.voice[0].playing = True
    output._mixer.voice[0].reset_mock()
    output.flush()

    assert output._loudness[0] == 0.75


def test_flush_updates_loudness_on_any_slot_index(tmp_path) -> None:
    """flush updates loudness on any slot, not just slot 0."""
    wav = tmp_path / "music.wav"
    wav.write_bytes(b"RIFF")

    registry = AudioRegistry()
    output = _make_output(registry, max_volume=0.4, num_voices=3)

    # Fill slots 0 and 1, then place the target receipt in slot 2
    _fill_pool(output, wav, registry, 2, loop=True)
    registry.register("music_2", str(wav))
    receipt = _make_receipt(loudness=1.0)
    output.handle_event(
        EffectEvent("pack", "music", "start"),
        frozenset({"ambient"}),
        _effect_loop("start", "music_2"),
        receipt,
    )

    receipt.loudness = 0.3
    output._mixer.voice[2].playing = True
    output.flush()

    assert output._loudness[2] == 0.3


# ---------------------------------------------------------------------------
# loudness — voice level set at playback start
# ---------------------------------------------------------------------------


def test_clip_sets_voice_level_from_receipt_loudness(tmp_path) -> None:
    """Voice level = max_volume * receipt.loudness when playback starts."""
    wav = tmp_path / "music.wav"
    wav.write_bytes(b"RIFF")

    registry = AudioRegistry()
    registry.register("music", str(wav))

    output = _make_output(registry, max_volume=0.4)
    effect = _effect_loop("start", "music")
    receipt = _make_receipt(loudness=0.5)

    output.handle_event(
        EffectEvent("pack", "effect", "start"), frozenset({"ambient"}), effect, receipt
    )

    assert output._mixer.voice[0].level == pytest.approx(0.4 * 0.5)
    assert output._loudness[0] == 0.5


# ---------------------------------------------------------------------------
# Eviction — full pool, oldest-first selection
# ---------------------------------------------------------------------------


def test_new_oneshot_evicts_oldest_oneshot_when_all_oneshots(tmp_path) -> None:
    """All N voices hold one-shots: new one-shot evicts the slot claimed first."""
    wav = tmp_path / "clip.wav"
    wav.write_bytes(b"RIFF")

    registry = AudioRegistry()
    registry.register("new_clip", str(wav))

    output = _make_output(registry, num_voices=2)
    old_receipts = _fill_pool(output, wav, registry, 2, loop=False)

    for v in output._mixer.voice:
        v.reset_mock()

    effect = _effect_oneshot("start", "new_clip")
    new_receipt = _make_receipt()
    output.handle_event(
        EffectEvent("rlgl", "clip", "start"), frozenset({"personal"}), effect, new_receipt
    )

    output._mixer.voice[0].stop.assert_called()
    output._mixer.voice[0].play.assert_called()
    assert output._receipts[0] is new_receipt
    old_receipts[0].stop.assert_not_called()


def test_new_loop_evicts_oldest_loop_when_all_loops(tmp_path) -> None:
    """All N voices hold loops: new loop evicts the slot claimed first."""
    wav = tmp_path / "music.wav"
    wav.write_bytes(b"RIFF")

    registry = AudioRegistry()
    registry.register("new_music", str(wav))

    output = _make_output(registry, num_voices=2)
    old_receipts = _fill_pool(output, wav, registry, 2, loop=True)

    for v in output._mixer.voice:
        v.reset_mock()

    effect = _effect_loop("start", "new_music")
    new_receipt = _make_receipt()
    output.handle_event(
        EffectEvent("rlgl", "music", "start"), frozenset({"ambient"}), effect, new_receipt
    )

    output._mixer.voice[0].stop.assert_called()
    output._mixer.voice[0].play.assert_called()
    assert output._receipts[0] is new_receipt
    old_receipts[0].stop.assert_not_called()


def test_new_loop_evicts_oldest_loop_not_oneshot_in_mixed_pool(tmp_path) -> None:
    """Mixed pool: new loop evicts oldest loop, not the older one-shot."""
    wav = tmp_path / "music.wav"
    wav.write_bytes(b"RIFF")

    registry = AudioRegistry()
    registry.register("new_music", str(wav))
    registry.register("clip_0", str(wav))
    registry.register("clip_1", str(wav))

    output = _make_output(registry, num_voices=2)

    # Slot 0 = older one-shot, slot 1 = newer loop
    r0 = _make_receipt()
    output.handle_event(
        EffectEvent("rlgl", "clip", "start"),
        frozenset({"personal"}),
        _effect_oneshot("start", "clip_0"),
        r0,
    )
    r1 = _make_receipt()
    output.handle_event(
        EffectEvent("rlgl", "clip", "start"),
        frozenset({"ambient"}),
        _effect_loop("start", "clip_1"),
        r1,
    )

    for v in output._mixer.voice:
        v.reset_mock()

    effect = _effect_loop("start", "new_music")
    new_receipt = _make_receipt()
    output.handle_event(
        EffectEvent("rlgl", "music", "start"), frozenset({"ambient"}), effect, new_receipt
    )

    # Slot 1 is the only loop — must be evicted even though it's newer
    output._mixer.voice[1].stop.assert_called()
    output._mixer.voice[1].play.assert_called()
    output._mixer.voice[0].play.assert_not_called()
    r1.stop.assert_not_called()


def test_new_oneshot_evicts_oldest_oneshot_not_loop_in_mixed_pool(tmp_path) -> None:
    """Mixed pool: new one-shot evicts oldest one-shot, not the older loop."""
    wav = tmp_path / "sting.wav"
    wav.write_bytes(b"RIFF")

    registry = AudioRegistry()
    registry.register("new_sting", str(wav))
    registry.register("clip_0", str(wav))
    registry.register("clip_1", str(wav))

    output = _make_output(registry, num_voices=2)

    # Slot 0 = older loop, slot 1 = newer one-shot
    r0 = _make_receipt()
    output.handle_event(
        EffectEvent("rlgl", "clip", "start"),
        frozenset({"ambient"}),
        _effect_loop("start", "clip_0"),
        r0,
    )
    r1 = _make_receipt()
    output.handle_event(
        EffectEvent("rlgl", "clip", "start"),
        frozenset({"personal"}),
        _effect_oneshot("start", "clip_1"),
        r1,
    )

    for v in output._mixer.voice:
        v.reset_mock()

    effect = _effect_oneshot("start", "new_sting")
    new_receipt = _make_receipt()
    output.handle_event(
        EffectEvent("rlgl", "sting", "start"), frozenset({"personal"}), effect, new_receipt
    )

    # Slot 1 is the only one-shot — evicted
    output._mixer.voice[1].stop.assert_called()
    output._mixer.voice[1].play.assert_called()
    output._mixer.voice[0].play.assert_not_called()
    r1.stop.assert_not_called()


def test_new_oneshot_silently_dropped_when_all_loops(tmp_path) -> None:
    """All voices hold loops: new one-shot is silently dropped."""
    wav = tmp_path / "sting.wav"
    wav.write_bytes(b"RIFF")

    registry = AudioRegistry()
    registry.register("new_sting", str(wav))

    output = _make_output(registry, num_voices=2)
    _fill_pool(output, wav, registry, 2, loop=True)

    for v in output._mixer.voice:
        v.reset_mock()

    effect = _effect_oneshot("start", "new_sting")
    new_receipt = _make_receipt()
    output.handle_event(
        EffectEvent("rlgl", "sting", "start"), frozenset({"personal"}), effect, new_receipt
    )

    output._mixer.voice[0].play.assert_not_called()
    output._mixer.voice[1].play.assert_not_called()


def test_new_loop_evicts_oldest_oneshot_when_no_loop_in_pool(tmp_path) -> None:
    """All voices hold one-shots: new loop falls back to evicting the oldest one-shot."""
    wav = tmp_path / "music.wav"
    wav.write_bytes(b"RIFF")

    registry = AudioRegistry()
    registry.register("new_music", str(wav))

    output = _make_output(registry, num_voices=2)
    old_receipts = _fill_pool(output, wav, registry, 2, loop=False)

    for v in output._mixer.voice:
        v.reset_mock()

    effect = _effect_loop("start", "new_music")
    new_receipt = _make_receipt()
    output.handle_event(
        EffectEvent("rlgl", "music", "start"), frozenset({"ambient"}), effect, new_receipt
    )

    output._mixer.voice[0].stop.assert_called()
    output._mixer.voice[0].play.assert_called()
    assert output._receipts[0] is new_receipt
    old_receipts[0].stop.assert_not_called()


def test_evicted_slot_not_re_evicted_on_next_eviction(tmp_path) -> None:
    """After eviction, the reclaimed slot is not evicted again — it becomes the newest claim."""
    wav = tmp_path / "clip.wav"
    wav.write_bytes(b"RIFF")

    registry = AudioRegistry()
    output = _make_output(registry, num_voices=3)
    _fill_pool(output, wav, registry, 3, loop=False)

    # First eviction — slot 0 (oldest) is evicted and reclaimed
    registry.register("evict_1", str(wav))
    output.handle_event(
        EffectEvent("rlgl", "clip", "start"),
        frozenset({"personal"}),
        _effect_oneshot("start", "evict_1"),
        _make_receipt(),
    )

    # Reset to isolate the second eviction
    for v in output._mixer.voice:
        v.reset_mock()

    # Second eviction — slot 1 (now oldest) should be evicted, NOT slot 0
    registry.register("evict_2", str(wav))
    output.handle_event(
        EffectEvent("rlgl", "clip", "start"),
        frozenset({"personal"}),
        _effect_oneshot("start", "evict_2"),
        _make_receipt(),
    )

    output._mixer.voice[1].stop.assert_called()
    output._mixer.voice[1].play.assert_called()
    output._mixer.voice[0].play.assert_not_called()
    output._mixer.voice[2].play.assert_not_called()


def test_evicted_slot_voice_stopped_and_new_clip_plays(tmp_path) -> None:
    """On eviction: mixer voice is stopped and the new clip plays on the evicted slot."""
    wav = tmp_path / "clip.wav"
    wav.write_bytes(b"RIFF")

    registry = AudioRegistry()
    registry.register("new_clip", str(wav))

    output = _make_output(registry, num_voices=2)
    _fill_pool(output, wav, registry, 2, loop=False)

    for v in output._mixer.voice:
        v.reset_mock()

    effect = _effect_oneshot("start", "new_clip")
    new_receipt = _make_receipt()
    output.handle_event(
        EffectEvent("rlgl", "clip", "start"), frozenset({"personal"}), effect, new_receipt
    )

    output._mixer.voice[0].stop.assert_called()
    output._mixer.voice[0].play.assert_called()
    assert output._receipts[0] is new_receipt


def test_evicted_receipt_is_not_stopped(tmp_path) -> None:
    """Evicted receipt is left alive — its lifecycle is managed by rules, not AudioEffectOutput."""
    wav = tmp_path / "clip.wav"
    wav.write_bytes(b"RIFF")

    registry = AudioRegistry()
    registry.register("new_clip", str(wav))

    output = _make_output(registry, num_voices=2)
    old_receipts = _fill_pool(output, wav, registry, 2, loop=False)

    effect = _effect_oneshot("start", "new_clip")
    new_receipt = _make_receipt()
    output.handle_event(
        EffectEvent("rlgl", "clip", "start"), frozenset({"personal"}), effect, new_receipt
    )

    old_receipts[0].stop.assert_not_called()
