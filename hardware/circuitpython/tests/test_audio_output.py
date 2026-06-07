"""Tests for AudioEffectOutput — the live VoiceSink adapter.

Voice-slot bookkeeping (claim/eviction/sweep, the audio-only receipt-stop rule,
loudness tracking) lives in ``VoicePool`` and is covered by ``test_voice_pool.py``.
These tests cover only what the adapter itself owns: the shell-routing guards in
``handle_event`` and the last-mile hardware mapping of the five ``VoiceSink``
methods onto the mixer and file handles.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from effects.effect import AudioPlaybackConfig, Effect, EffectAudio, EffectPixels
from engine.audio import AudioRegistry
from engine.events import EffectEvent
from engine.state import EffectReceipt

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
) -> tuple[object, MagicMock]:
    """Build an AudioEffectOutput with all hardware deps patched out.

    Returns the output and the mock mixer it was constructed with, so tests can
    observe last-mile calls without reaching into private attributes.
    """
    import audiobusio  # type: ignore[import]
    import audiocore  # type: ignore[import]
    import audiomixer  # type: ignore[import]

    audiobusio.I2SOut = MagicMock(return_value=MagicMock())
    audiocore.WaveFile = MagicMock(return_value=MagicMock())
    mock_mixer = MagicMock()
    mock_mixer.voice = [MagicMock() for _ in range(num_voices)]
    audiomixer.Mixer = MagicMock(return_value=mock_mixer)

    from hardware.circuitpython.audio_output import AudioEffectOutput

    output = AudioEffectOutput(
        audio_registry=audio_registry, max_volume=max_volume, num_voices=num_voices
    )
    return output, mock_mixer


def _effect_oneshot(verb: str, clip_name: str) -> Effect:
    """One-shot effect with pixels (not audio-only)."""
    return Effect(
        name="test",
        pixels=MagicMock(spec=EffectPixels),
        audio=EffectAudio(clips={verb: AudioPlaybackConfig(name=clip_name, loop=False)}),
    )


def _effect_loop(verb: str, clip_name: str) -> Effect:
    """Loop effect with pixels (not audio-only)."""
    return Effect(
        name="test",
        pixels=MagicMock(spec=EffectPixels),
        audio=EffectAudio(clips={verb: AudioPlaybackConfig(name=clip_name, loop=True)}),
    )


def _effect_audio_only(verb: str, clip_name: str) -> Effect:
    """One-shot effect with audio only (no pixels, no vibration)."""
    return Effect(
        name="audio_only",
        audio=EffectAudio(clips={verb: AudioPlaybackConfig(name=clip_name, loop=False)}),
    )


def _register_wav(tmp_path, registry: AudioRegistry, name: str) -> str:
    wav = tmp_path / f"{name}.wav"
    wav.write_bytes(b"RIFF")
    registry.register(name, str(wav))
    return str(wav)


# ---------------------------------------------------------------------------
# Constructor
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
    assert audiomixer.Mixer.call_args[1]["voice_count"] == 4


# ---------------------------------------------------------------------------
# handle_event — shell-routing guards (no claim → no playback)
# ---------------------------------------------------------------------------


def test_handle_event_ignores_effect_with_no_audio() -> None:
    """effect.audio is None → no play, no crash."""
    output, mixer = _make_output(AudioRegistry())

    output.handle_event(
        EffectEvent("rlgl", "silent", "start"),
        frozenset({"personal"}),
        Effect(name="silent"),
        _make_receipt(),
    )

    mixer.voice[0].play.assert_not_called()
    mixer.voice[1].play.assert_not_called()


def test_handle_event_ignores_unknown_verb() -> None:
    """Verb not in clips → no play, no crash."""
    output, mixer = _make_output(AudioRegistry())

    output.handle_event(
        EffectEvent("rlgl", "effect", "stop"),
        frozenset({"personal"}),
        _effect_oneshot("peak", "some_peak"),
        _make_receipt(),
    )

    mixer.voice[0].play.assert_not_called()
    mixer.voice[1].play.assert_not_called()


def test_handle_event_ignores_unregistered_clip() -> None:
    """Clip name not in AudioRegistry → no play, no crash."""
    output, mixer = _make_output(AudioRegistry())

    output.handle_event(
        EffectEvent("rlgl", "effect", "start"),
        frozenset({"personal"}),
        _effect_oneshot("start", "missing_clip"),
        _make_receipt(),
    )

    mixer.voice[0].play.assert_not_called()
    mixer.voice[1].play.assert_not_called()


def test_handle_event_ignores_oserror_on_file_open(tmp_path) -> None:
    """OSError opening the WAV file → no play, no crash."""
    registry = AudioRegistry()
    registry.register("missing", str(tmp_path / "nonexistent.wav"))
    output, mixer = _make_output(registry)

    output.handle_event(
        EffectEvent("rlgl", "effect", "start"),
        frozenset({"personal"}),
        _effect_oneshot("start", "missing"),
        _make_receipt(),
    )

    mixer.voice[0].play.assert_not_called()
    mixer.voice[1].play.assert_not_called()


# ---------------------------------------------------------------------------
# handle_event — routing a valid clip into the pool reaches the hardware
# ---------------------------------------------------------------------------


def test_valid_clip_plays_on_an_idle_voice(tmp_path) -> None:
    """A registered clip is opened and played on a mixer voice at the receipt's loudness."""
    registry = AudioRegistry()
    _register_wav(tmp_path, registry, "music")
    output, mixer = _make_output(registry, max_volume=0.4)

    output.handle_event(
        EffectEvent("rlgl", "music", "start"),
        frozenset({"ambient"}),
        _effect_loop("start", "music"),
        _make_receipt(loudness=0.5),
    )

    mixer.voice[0].play.assert_called_once()
    assert mixer.voice[0].play.call_args[1]["loop"] is True
    assert mixer.voice[0].level == pytest.approx(0.4 * 0.5)


def test_audio_only_clip_routes_as_audio_only(tmp_path) -> None:
    """An effect with no pixels/vibration is claimed as audio-only: its receipt is

    stopped when the clip finishes naturally (the adapter computes audio_only from
    effect shape; the pool acts on it)."""
    registry = AudioRegistry()
    _register_wav(tmp_path, registry, "sting")
    output, mixer = _make_output(registry)
    receipt = _make_receipt()

    output.handle_event(
        EffectEvent("rlgl", "sting", "start"),
        frozenset({"personal"}),
        _effect_audio_only("start", "sting"),
        receipt,
    )

    mixer.voice[0].playing = False
    output.flush()

    receipt.stop.assert_called_once()


def test_clip_with_pixels_routes_as_not_audio_only(tmp_path) -> None:
    """An effect with pixels is not audio-only: its receipt is left to rules on finish."""
    registry = AudioRegistry()
    _register_wav(tmp_path, registry, "sting")
    output, mixer = _make_output(registry)
    receipt = _make_receipt()

    output.handle_event(
        EffectEvent("rlgl", "sting", "start"),
        frozenset({"personal"}),
        _effect_oneshot("start", "sting"),
        receipt,
    )

    mixer.voice[0].playing = False
    output.flush()

    receipt.stop.assert_not_called()


# ---------------------------------------------------------------------------
# VoiceSink — last-mile hardware mapping
# ---------------------------------------------------------------------------


def test_open_source_opens_file_and_wraps_wavefile(tmp_path) -> None:
    """open_source opens the path and bundles the file with a WaveFile, file left open."""
    import audiocore  # type: ignore[import]

    wav = tmp_path / "clip.wav"
    wav.write_bytes(b"RIFF")
    output, _ = _make_output(AudioRegistry())

    source = output.open_source(str(wav))

    f, wave = source
    audiocore.WaveFile.assert_called_once_with(f)
    assert wave is audiocore.WaveFile.return_value
    assert not f.closed  # file stays open while playing
    f.close()


def test_open_source_returns_none_on_oserror(tmp_path) -> None:
    """open_source returns None when the file cannot be opened."""
    output, _ = _make_output(AudioRegistry())

    assert output.open_source(str(tmp_path / "nope.wav")) is None


def test_play_stores_source_and_plays_wave_with_loop(tmp_path) -> None:
    """play hands the WaveFile to the slot's voice with the loop flag."""
    wav = tmp_path / "clip.wav"
    wav.write_bytes(b"RIFF")
    output, mixer = _make_output(AudioRegistry())
    source = output.open_source(str(wav))
    _, wave = source

    output.play(1, source, loop=True)

    mixer.voice[1].play.assert_called_once_with(wave, loop=True)
    output.stop(1)  # cleanup: close the file


def test_stop_stops_voice_and_closes_file(tmp_path) -> None:
    """stop stops the slot's voice and closes the open WAV file."""
    wav = tmp_path / "clip.wav"
    wav.write_bytes(b"RIFF")
    output, mixer = _make_output(AudioRegistry())
    source = output.open_source(str(wav))
    f, _ = source
    output.play(0, source, loop=False)

    output.stop(0)

    mixer.voice[0].stop.assert_called_once()
    assert f.closed


def test_stop_on_idle_slot_stops_voice_without_error(tmp_path) -> None:
    """stop on a slot with no open source still stops the voice and does not raise."""
    output, mixer = _make_output(AudioRegistry())

    output.stop(0)

    mixer.voice[0].stop.assert_called_once()


def test_set_loudness_applies_max_volume(tmp_path) -> None:
    """set_loudness sets the voice level to max_volume * loudness."""
    output, mixer = _make_output(AudioRegistry(), max_volume=0.4)

    output.set_loudness(0, 0.5)

    assert mixer.voice[0].level == pytest.approx(0.4 * 0.5)


def test_is_playing_reads_voice_playing(tmp_path) -> None:
    """is_playing reports the slot voice's playing flag."""
    output, mixer = _make_output(AudioRegistry())

    mixer.voice[0].playing = True
    mixer.voice[1].playing = False

    assert output.is_playing(0) is True
    assert output.is_playing(1) is False
