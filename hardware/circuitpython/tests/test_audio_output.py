"""Tests for AudioEffectOutput — EffectAudio-based clip lookup."""

from __future__ import annotations

from unittest.mock import MagicMock

from effects.effect import AudioPlaybackConfig, Effect, EffectAudio
from engine.audio import AudioRegistry
from engine.events import EffectEvent
from engine.state import EffectReceipt
from hardware.circuitpython.audio_output import AudioEffectOutput

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_receipt() -> MagicMock:
    r = MagicMock(spec=EffectReceipt)
    r.is_stopped.return_value = False
    return r


def _make_output(audio_registry: AudioRegistry) -> AudioEffectOutput:
    """Build an AudioEffectOutput with all hardware deps patched out."""
    import audiobusio  # type: ignore[import]
    import audiocore  # type: ignore[import]
    import audiomixer  # type: ignore[import]

    audiobusio.I2SOut = MagicMock(return_value=MagicMock())
    audiocore.WaveFile = MagicMock(return_value=MagicMock())
    mock_mixer = MagicMock()
    mock_voice0 = MagicMock()
    mock_voice1 = MagicMock()
    mock_mixer.voice = [mock_voice0, mock_voice1]
    audiomixer.Mixer = MagicMock(return_value=mock_mixer)

    from hardware.circuitpython.audio_output import AudioEffectOutput

    return AudioEffectOutput(audio_registry=audio_registry)


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
# Voice selection — loop vs one-shot
# ---------------------------------------------------------------------------


def test_loop_clip_plays_on_voice_0(tmp_path) -> None:
    """loop=True clips play on voice 0."""
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


def test_oneshot_clip_plays_on_voice_1(tmp_path) -> None:
    """loop=False clips play on voice 1."""
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

    output._mixer.voice[1].play.assert_called()
    output._mixer.voice[0].play.assert_not_called()


def test_peak_verb_with_loop_false_plays_on_voice_1(tmp_path) -> None:
    """peak verb with loop=False plays on voice 1."""
    wav = tmp_path / "warning_sting_peak.wav"
    wav.write_bytes(b"RIFF")

    registry = AudioRegistry()
    registry.register("warning_sting_peak", str(wav))

    output = _make_output(registry)
    effect = _effect_oneshot("peak", "warning_sting_peak")
    receipt = _make_receipt()

    output.handle_event(
        EffectEvent("rlgl", "warning_sting", "peak"), frozenset({"personal"}), effect, receipt
    )

    output._mixer.voice[1].play.assert_called()
    output._mixer.voice[0].play.assert_not_called()


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

    output._mixer.voice[1].stop.assert_not_called()
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

    output._mixer.voice[1].play.assert_not_called()


# ---------------------------------------------------------------------------
# One-shot replacement on voice 1
# ---------------------------------------------------------------------------


def test_new_oneshot_stops_and_replaces_existing_oneshot(tmp_path) -> None:
    """A new one-shot event stops the existing voice 1 playback before starting."""
    wav = tmp_path / "sting.wav"
    wav.write_bytes(b"RIFF")

    registry = AudioRegistry()
    registry.register("sting_start", str(wav))

    output = _make_output(registry)

    old_receipt = _make_receipt()
    old_file = MagicMock()
    output._once_file = old_file
    output._once_receipt = old_receipt
    output._once_verb = "start"

    effect = _effect_oneshot("start", "sting_start")
    receipt = _make_receipt()
    output.handle_event(
        EffectEvent("rlgl", "sting", "start"), frozenset({"personal"}), effect, receipt
    )

    output._mixer.voice[1].stop.assert_called()
    old_file.close.assert_called()
    old_receipt.stop.assert_called()


def test_replacing_peak_oneshot_does_not_stop_pixel_effect_receipt(tmp_path) -> None:
    """Replacing a 'peak' one-shot does NOT stop the pixel effect's receipt."""
    wav = tmp_path / "pulse_peak.wav"
    wav.write_bytes(b"RIFF")

    registry = AudioRegistry()
    registry.register("pulse_peak", str(wav))

    output = _make_output(registry)

    old_receipt = _make_receipt()
    old_file = MagicMock()
    output._once_file = old_file
    output._once_receipt = old_receipt
    output._once_verb = "peak"

    effect = _effect_oneshot("peak", "pulse_peak")
    receipt = _make_receipt()
    output.handle_event(
        EffectEvent("rlgl", "pulse", "peak"), frozenset({"personal"}), effect, receipt
    )

    output._mixer.voice[1].stop.assert_called()
    old_file.close.assert_called()
    old_receipt.stop.assert_not_called()


# ---------------------------------------------------------------------------
# flush — natural end-of-playback and external stop
# ---------------------------------------------------------------------------


def test_flush_stops_oneshot_receipt_when_voice1_finishes_naturally() -> None:
    """flush: voice 1 finishes playing → receipt is stopped and file is closed."""
    registry = AudioRegistry()
    output = _make_output(registry)

    receipt = _make_receipt()
    once_file = MagicMock()
    output._once_receipt = receipt
    output._once_file = once_file
    output._once_verb = "start"
    output._mixer.voice[1].playing = False

    output.flush()

    receipt.stop.assert_called_once()
    once_file.close.assert_called_once()
    assert output._once_receipt is None
    assert output._once_file is None
    assert output._once_wave is None


def test_flush_does_not_stop_pixel_effect_receipt_when_peak_sound_finishes() -> None:
    """flush: voice 1 finishes a 'peak' sound → pixel effect receipt is NOT stopped."""
    registry = AudioRegistry()
    output = _make_output(registry)

    receipt = _make_receipt()
    once_file = MagicMock()
    output._once_receipt = receipt
    output._once_file = once_file
    output._once_verb = "peak"
    output._mixer.voice[1].playing = False

    output.flush()

    receipt.stop.assert_not_called()
    once_file.close.assert_called_once()
    assert output._once_receipt is None
    assert output._once_file is None
    assert output._once_wave is None


def test_flush_stops_voice1_early_when_receipt_externally_stopped() -> None:
    """flush: externally-stopped receipt causes voice 1 to halt and file to close."""
    registry = AudioRegistry()
    output = _make_output(registry)

    receipt = _make_receipt()
    receipt.is_stopped.return_value = True
    once_file = MagicMock()
    output._once_receipt = receipt
    output._once_file = once_file
    output._mixer.voice[1].playing = True

    output.flush()

    output._mixer.voice[1].stop.assert_called_once()
    once_file.close.assert_called_once()
    assert output._once_receipt is None
    assert output._once_wave is None


def test_flush_stops_voice0_when_loop_receipt_externally_stopped() -> None:
    """flush: externally-stopped loop receipt causes voice 0 to halt and file to close."""
    registry = AudioRegistry()
    output = _make_output(registry)

    loop_receipt = _make_receipt()
    loop_receipt.is_stopped.return_value = True
    loop_file = MagicMock()
    output._loop_receipt = loop_receipt
    output._loop_file = loop_file

    output.flush()

    output._mixer.voice[0].stop.assert_called_once()
    loop_file.close.assert_called_once()
    assert output._loop_receipt is None
    assert output._loop_file is None
    assert output._loop_wave is None


def test_flush_does_nothing_when_voice1_still_playing() -> None:
    """flush: active one-shot with externally-alive receipt is left running."""
    registry = AudioRegistry()
    output = _make_output(registry)

    receipt = _make_receipt()
    receipt.is_stopped.return_value = False
    output._once_receipt = receipt
    output._mixer.voice[1].playing = True

    output.flush()

    output._mixer.voice[1].stop.assert_not_called()
    receipt.stop.assert_not_called()
