"""Tests for AudioEffectOutput — unified verb-based sound lookup (issue #215, PR #219)."""

from __future__ import annotations

from unittest.mock import MagicMock

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


def _make_output(registry: MagicMock) -> AudioEffectOutput:
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

    output = AudioEffectOutput(registry=registry)
    return output


# ---------------------------------------------------------------------------
# Unified verb lookup — happy path
# ---------------------------------------------------------------------------


def test_verb_event_plays_named_wav_on_voice_1(tmp_path) -> None:
    """Any verb: look up via sound_path(event) and play on voice 1."""
    wav = tmp_path / "shield_alert.wav"
    wav.write_bytes(b"RIFF")

    registry = MagicMock()
    registry.sound_path.return_value = str(wav)

    output = _make_output(registry)
    event = EffectEvent("mygame", "shield", "alert")
    receipt = _make_receipt()

    output.handle_event(event, frozenset({"personal"}), MagicMock(), receipt)

    registry.sound_path.assert_called_once_with(event)
    output._mixer.voice[1].stop.assert_called_once()
    output._mixer.voice[1].play.assert_called()


def test_start_verb_plays_oneshot_on_voice_1(tmp_path) -> None:
    """start verb is no longer special — plays one-shot on voice 1 like any other verb."""
    wav = tmp_path / "sting_start.wav"
    wav.write_bytes(b"RIFF")

    registry = MagicMock()
    registry.sound_path.return_value = str(wav)

    output = _make_output(registry)
    event = EffectEvent("mygame", "sting", "start")
    receipt = _make_receipt()

    output.handle_event(event, frozenset({"personal"}), MagicMock(), receipt)

    registry.sound_path.assert_called_once_with(event)
    output._mixer.voice[1].play.assert_called()
    output._mixer.voice[0].play.assert_not_called()


def test_start_verb_with_ambient_scope_plays_oneshot_not_loop(tmp_path) -> None:
    """start+ambient no longer triggers loop — same one-shot path as everything else."""
    wav = tmp_path / "music_start.wav"
    wav.write_bytes(b"RIFF")

    registry = MagicMock()
    registry.sound_path.return_value = str(wav)

    output = _make_output(registry)
    event = EffectEvent("mygame", "music", "start")
    receipt = _make_receipt()

    output.handle_event(event, frozenset({"ambient"}), MagicMock(), receipt)

    output._mixer.voice[1].play.assert_called()
    output._mixer.voice[0].play.assert_not_called()


def test_verb_event_replaces_current_voice1_oneshot(tmp_path) -> None:
    """A new verb event stops the existing voice 1 one-shot before playing."""
    wav = tmp_path / "shield_boom.wav"
    wav.write_bytes(b"RIFF")

    registry = MagicMock()
    registry.sound_path.return_value = str(wav)

    output = _make_output(registry)

    # Simulate an already-playing one-shot from a prior "start" event
    old_receipt = _make_receipt()
    old_file = MagicMock()
    output._once_file = old_file
    output._once_receipt = old_receipt
    output._once_verb = "start"

    event = EffectEvent("mygame", "shield", "boom")
    receipt = _make_receipt()
    output.handle_event(event, frozenset({"personal"}), MagicMock(), receipt)

    output._mixer.voice[1].stop.assert_called()
    old_file.close.assert_called()
    old_receipt.stop.assert_called()


def test_peak_event_replacing_current_oneshot_does_not_stop_pixel_effect_receipt(
    tmp_path,
) -> None:
    """Replacing a 'peak' one-shot does NOT stop the pixel effect's receipt."""
    wav = tmp_path / "pulse_peak.wav"
    wav.write_bytes(b"RIFF")

    registry = MagicMock()
    registry.sound_path.return_value = str(wav)

    output = _make_output(registry)

    # Simulate an already-playing one-shot from a prior "peak" event
    old_receipt = _make_receipt()
    old_file = MagicMock()
    output._once_file = old_file
    output._once_receipt = old_receipt
    output._once_verb = "peak"

    event = EffectEvent("mygame", "pulse", "peak")
    receipt = _make_receipt()
    output.handle_event(event, frozenset({"personal"}), MagicMock(), receipt)

    output._mixer.voice[1].stop.assert_called()
    old_file.close.assert_called()
    # Receipt must NOT be stopped — it belongs to the still-running pixel effect
    old_receipt.stop.assert_not_called()


# ---------------------------------------------------------------------------
# Unified verb lookup — missing path / errors
# ---------------------------------------------------------------------------


def test_verb_event_silently_ignored_when_no_sound_path() -> None:
    """registry.sound_path returns None → no play, no crash."""
    registry = MagicMock()
    registry.sound_path.return_value = None

    output = _make_output(registry)
    event = EffectEvent("mygame", "shield", "alert")
    receipt = _make_receipt()

    # Should not raise
    output.handle_event(event, frozenset({"personal"}), MagicMock(), receipt)

    output._mixer.voice[1].stop.assert_not_called()
    output._mixer.voice[1].play.assert_not_called()


def test_verb_event_silently_ignored_on_oserror(tmp_path) -> None:
    """OSError opening the file → no play, no crash."""
    registry = MagicMock()
    registry.sound_path.return_value = str(tmp_path / "nonexistent.wav")

    output = _make_output(registry)
    event = EffectEvent("mygame", "shield", "alert")
    receipt = _make_receipt()

    # Should not raise even though the file does not exist
    output.handle_event(event, frozenset({"personal"}), MagicMock(), receipt)

    output._mixer.voice[1].play.assert_not_called()


def test_stop_verb_silently_ignored_when_no_sound_path() -> None:
    """stop with no matching sound: loop still stops, no one-shot played."""
    registry = MagicMock()
    registry.sound_path.return_value = None

    output = _make_output(registry)
    loop_receipt = _make_receipt()
    output._loop_receipt = loop_receipt

    event = EffectEvent("mygame", "music", "stop")
    output.handle_event(event, frozenset({"ambient"}), MagicMock(), loop_receipt)

    output._mixer.voice[0].stop.assert_called()
    output._mixer.voice[1].play.assert_not_called()


# ---------------------------------------------------------------------------
# stop verb — loop stop behavior preserved
# ---------------------------------------------------------------------------


def test_stop_verb_stops_voice_0_loop() -> None:
    """stop verb: matching loop receipt causes voice 0 to stop."""
    registry = MagicMock()
    registry.sound_path.return_value = None

    output = _make_output(registry)

    loop_receipt = _make_receipt()
    output._loop_receipt = loop_receipt

    event = EffectEvent("mygame", "music", "stop")
    output.handle_event(event, frozenset({"ambient"}), MagicMock(), loop_receipt)

    output._mixer.voice[0].stop.assert_called()


def test_stop_verb_does_not_stop_voice_0_for_unrelated_receipt() -> None:
    """stop verb with a different receipt does not stop the loop."""
    registry = MagicMock()
    registry.sound_path.return_value = None

    output = _make_output(registry)

    loop_receipt = _make_receipt()
    output._loop_receipt = loop_receipt

    event = EffectEvent("mygame", "music", "stop")
    other_receipt = _make_receipt()
    output.handle_event(event, frozenset({"ambient"}), MagicMock(), other_receipt)

    output._mixer.voice[0].stop.assert_not_called()


# ---------------------------------------------------------------------------
# flush — natural end-of-playback and external stop
# ---------------------------------------------------------------------------


def test_flush_stops_oneshot_receipt_when_voice1_finishes_naturally() -> None:
    """flush: voice 1 finishes playing → receipt is stopped and file is closed."""
    registry = MagicMock()
    output = _make_output(registry)

    receipt = _make_receipt()
    once_file = MagicMock()
    output._once_receipt = receipt
    output._once_file = once_file
    output._once_verb = "start"  # lifecycle: stopping receipt is correct
    output._mixer.voice[1].playing = False

    output.flush()

    receipt.stop.assert_called_once()
    once_file.close.assert_called_once()
    assert output._once_receipt is None
    assert output._once_file is None
    assert output._once_wave is None


def test_flush_does_not_stop_pixel_effect_receipt_when_peak_sound_finishes() -> None:
    """flush: voice 1 finishes a 'peak' sound → pixel effect receipt is NOT stopped."""
    registry = MagicMock()
    output = _make_output(registry)

    receipt = _make_receipt()
    once_file = MagicMock()
    output._once_receipt = receipt
    output._once_file = once_file
    output._once_verb = "peak"  # side-effect sound: must not kill the pixel effect
    output._mixer.voice[1].playing = False

    output.flush()

    receipt.stop.assert_not_called()
    once_file.close.assert_called_once()
    assert output._once_receipt is None
    assert output._once_file is None
    assert output._once_wave is None


def test_flush_stops_voice1_early_when_receipt_externally_stopped() -> None:
    """flush: externally-stopped receipt causes voice 1 to halt and file to close."""
    registry = MagicMock()
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
    registry = MagicMock()
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


def test_flush_does_nothing_when_voice1_still_playing() -> None:
    """flush: active one-shot with externally-alive receipt is left running."""
    registry = MagicMock()
    output = _make_output(registry)

    receipt = _make_receipt()
    receipt.is_stopped.return_value = False
    output._once_receipt = receipt
    output._mixer.voice[1].playing = True

    output.flush()

    output._mixer.voice[1].stop.assert_not_called()
    receipt.stop.assert_not_called()
