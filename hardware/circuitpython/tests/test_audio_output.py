"""Tests for AudioEffectOutput — flat N-voice pool with idle-first selection."""

from __future__ import annotations

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

    # Occupy slot 0 manually
    output._receipts[0] = _make_receipt()

    effect = _effect_oneshot("start", "clip_b")
    receipt = _make_receipt()
    output.handle_event(
        EffectEvent("rlgl", "clip", "start"), frozenset({"personal"}), effect, receipt
    )

    output._mixer.voice[0].play.assert_not_called()
    output._mixer.voice[1].play.assert_called()


def test_clip_silently_dropped_when_all_voices_occupied(tmp_path) -> None:
    """With all voices occupied, a new clip is silently dropped — no play, no crash."""
    wav = tmp_path / "clip.wav"
    wav.write_bytes(b"RIFF")

    registry = AudioRegistry()
    registry.register("new_clip", str(wav))

    output = _make_output(registry, num_voices=2)

    # Occupy all slots
    output._receipts[0] = _make_receipt()
    output._receipts[1] = _make_receipt()

    effect = _effect_oneshot("start", "new_clip")
    receipt = _make_receipt()
    output.handle_event(
        EffectEvent("rlgl", "clip", "start"), frozenset({"personal"}), effect, receipt
    )

    output._mixer.voice[0].play.assert_not_called()
    output._mixer.voice[1].play.assert_not_called()


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


def test_flush_frees_slot_when_oneshot_finishes_naturally() -> None:
    """flush: voice finishes playing naturally → slot freed, receipt NOT stopped."""
    registry = AudioRegistry()
    output = _make_output(registry)

    receipt = _make_receipt()
    wave_file = MagicMock()
    output._receipts[0] = receipt
    output._wave_files[0] = wave_file
    output._is_loop[0] = False
    output._mixer.voice[0].playing = False

    output.flush()

    receipt.stop.assert_not_called()
    wave_file.close.assert_called_once()
    assert output._receipts[0] is None
    assert output._wave_files[0] is None
    assert output._wave_objs[0] is None


def test_flush_frees_slot_on_any_index(tmp_path) -> None:
    """flush detects natural one-shot finish on any slot index, not just slot 0."""
    registry = AudioRegistry()
    output = _make_output(registry, num_voices=3)

    receipt = _make_receipt()
    wave_file = MagicMock()
    # Occupy slot 2 only (slots 0 and 1 idle)
    output._receipts[2] = receipt
    output._wave_files[2] = wave_file
    output._is_loop[2] = False
    output._mixer.voice[2].playing = False

    output.flush()

    receipt.stop.assert_not_called()
    wave_file.close.assert_called_once()
    assert output._receipts[2] is None


def test_flush_does_not_free_loop_slot_when_still_playing() -> None:
    """flush: loop voice still playing and receipt alive → slot not freed."""
    registry = AudioRegistry()
    output = _make_output(registry)

    receipt = _make_receipt()
    output._receipts[0] = receipt
    output._is_loop[0] = True
    output._mixer.voice[0].playing = True

    output.flush()

    assert output._receipts[0] is receipt
    output._mixer.voice[0].stop.assert_not_called()


# ---------------------------------------------------------------------------
# flush — externally-stopped receipt
# ---------------------------------------------------------------------------


def test_flush_stops_voice_and_frees_slot_when_receipt_externally_stopped() -> None:
    """flush: externally-stopped receipt → voice stopped, file closed, slot freed."""
    registry = AudioRegistry()
    output = _make_output(registry)

    receipt = _make_receipt()
    receipt.is_stopped.return_value = True
    wave_file = MagicMock()
    output._receipts[0] = receipt
    output._wave_files[0] = wave_file
    output._mixer.voice[0].playing = True

    output.flush()

    output._mixer.voice[0].stop.assert_called_once()
    wave_file.close.assert_called_once()
    assert output._receipts[0] is None
    assert output._wave_files[0] is None
    assert output._wave_objs[0] is None


def test_flush_clears_natural_finish_before_stopped_check() -> None:
    """flush: naturally-finished slot clears receipt before stopped check — no double processing."""
    registry = AudioRegistry()
    output = _make_output(registry)

    # Receipt that reports stopped=True
    receipt = _make_receipt()
    receipt.is_stopped.return_value = True
    wave_file = MagicMock()
    output._receipts[0] = receipt
    output._wave_files[0] = wave_file
    output._is_loop[0] = False
    # Simulate natural finish (voice not playing)
    output._mixer.voice[0].playing = False

    output.flush()

    # Natural finish cleared first, so stopped check sees receipt=None and skips
    # voice.stop should NOT be called (natural finish path doesn't call stop)
    output._mixer.voice[0].stop.assert_not_called()
    assert output._receipts[0] is None


# ---------------------------------------------------------------------------
# flush — per-slot loudness updates
# ---------------------------------------------------------------------------


def test_flush_updates_loudness_when_receipt_loudness_changes() -> None:
    """flush: receipt.loudness changed since last tick → voice level reapplied."""
    registry = AudioRegistry()
    output = _make_output(registry, max_volume=0.4)

    receipt = _make_receipt(loudness=0.5)
    receipt.is_stopped.return_value = False
    output._receipts[0] = receipt
    output._loudness[0] = 1.0
    output._mixer.voice[0].playing = True

    output.flush()

    assert output._mixer.voice[0].level == pytest.approx(0.4 * 0.5)
    assert output._loudness[0] == 0.5


def test_flush_does_not_update_loudness_when_unchanged() -> None:
    """flush: receipt.loudness unchanged → voice level not reapplied."""
    registry = AudioRegistry()
    output = _make_output(registry, max_volume=0.4)

    receipt = _make_receipt(loudness=0.75)
    receipt.is_stopped.return_value = False
    output._receipts[0] = receipt
    output._loudness[0] = 0.75
    output._mixer.voice[0].playing = True

    # Reset mock to track new calls only
    output._mixer.voice[0].reset_mock()

    output.flush()

    # level should not have been set
    assert output._loudness[0] == 0.75


def test_flush_updates_loudness_on_any_slot_index() -> None:
    """flush updates loudness on any slot, not just slot 0."""
    registry = AudioRegistry()
    output = _make_output(registry, max_volume=0.4, num_voices=3)

    receipt = _make_receipt(loudness=0.3)
    receipt.is_stopped.return_value = False
    output._receipts[2] = receipt
    output._loudness[2] = 1.0
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
