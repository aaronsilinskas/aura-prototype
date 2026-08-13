"""Tests for AudioEffectOutput — the live VoiceSink adapter.

Voice-slot bookkeeping (claim/eviction/sweep, the stops-receipt release rule,
loudness tracking) lives in ``VoicePool`` and is covered by ``test_voice_pool.py``.
These tests cover only what the adapter itself owns: the shell-routing guards in
``handle_event`` and the last-mile hardware mapping of the five ``VoiceSink``
methods onto the mixer and file handles.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from effects.effect import AudioPlaybackConfig, Effect, EffectAudio, EffectHaptic, EffectPixels
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


_FAKE_BIT_CLOCK = object()
_FAKE_WORD_SELECT = object()
_FAKE_DATA = object()


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
        audio_registry=audio_registry,
        max_volume=max_volume,
        num_voices=num_voices,
        i2s_bit_clock=_FAKE_BIT_CLOCK,
        i2s_word_select=_FAKE_WORD_SELECT,
        i2s_data=_FAKE_DATA,
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
    """One-shot effect with audio only (no pixels, no haptic)."""
    return Effect(
        name="audio_only",
        audio=EffectAudio(clips={verb: AudioPlaybackConfig(name=clip_name, loop=False)}),
    )


def _effect_oneshot_stops_effect(verb: str, clip_name: str) -> Effect:
    """One-shot effect with pixels and stops_effect=True."""
    return Effect(
        name="test",
        pixels=MagicMock(spec=EffectPixels),
        audio=EffectAudio(
            clips={verb: AudioPlaybackConfig(name=clip_name, loop=False, stops_effect=True)}
        ),
    )


def _effect_oneshot_with_haptic_stops_effect(verb: str, clip_name: str) -> Effect:
    """One-shot effect with pixels, haptic, and stops_effect=True."""
    return Effect(
        name="test",
        pixels=MagicMock(spec=EffectPixels),
        haptic=MagicMock(spec=EffectHaptic),
        audio=EffectAudio(
            clips={verb: AudioPlaybackConfig(name=clip_name, loop=False, stops_effect=True)}
        ),
    )


_TEST_PACK = "test_pack"


def _register_wav(tmp_path, registry: AudioRegistry, name: str) -> str:
    """Write ``<name>.wav`` under *tmp_path*, scan it into *registry*'s base
    under the fixed ``test_pack`` prefix, and return the qualified clip name
    (``"test_pack.<name>"``) an ``AudioPlaybackConfig`` should reference.

    Re-scans the whole directory on every call (``scan_pack_sounds`` merges
    rather than replaces), so registering a second clip in the same
    *tmp_path* never drops an earlier one.
    """
    wav = tmp_path / f"{name}.wav"
    wav.write_bytes(b"RIFF")
    registry.scan_pack_sounds(_TEST_PACK, str(tmp_path))
    return f"{_TEST_PACK}.{name}"


def _register_missing_path(registry: AudioRegistry, name: str, path: str) -> str:
    """Point a scene-overlay clip at *path* without creating the file, for
    OSError-on-open tests. Returns the qualified ``"scene.<name>"`` clip name."""
    registry.set_scene_sounds({name: path})
    return f"scene.{name}"


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


def test_i2sout_constructed_with_caller_supplied_pins() -> None:
    """audiobusio.I2SOut is constructed with the caller-supplied I2S pins."""
    import audiobusio  # type: ignore[import]

    registry = AudioRegistry()
    _make_output(registry)

    audiobusio.I2SOut.assert_called_once_with(_FAKE_BIT_CLOCK, _FAKE_WORD_SELECT, _FAKE_DATA)


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


def test_handle_event_raises_when_clip_name_is_unregistered() -> None:
    """A clip name AudioRegistry can't resolve propagates its ValueError (#804)
    -- handle_event no longer swallows the resolution failure into a no-op."""
    output, mixer = _make_output(AudioRegistry())

    with pytest.raises(ValueError):
        output.handle_event(
            EffectEvent("rlgl", "effect", "start"),
            frozenset({"personal"}),
            _effect_oneshot("start", "test_pack.missing_clip"),
            _make_receipt(),
        )

    mixer.voice[0].play.assert_not_called()
    mixer.voice[1].play.assert_not_called()


def test_handle_event_ignores_oserror_on_file_open(tmp_path) -> None:
    """A registered path whose file can't be opened → no play, no crash --
    distinct from an unresolvable clip name, this failure is VoicePool's own
    OSError guard around open_source, not AudioRegistry.path raising."""
    registry = AudioRegistry()
    clip_name = _register_missing_path(registry, "missing", str(tmp_path / "nonexistent.wav"))
    output, mixer = _make_output(registry)

    output.handle_event(
        EffectEvent("rlgl", "effect", "start"),
        frozenset({"personal"}),
        _effect_oneshot("start", clip_name),
        _make_receipt(),
    )

    mixer.voice[0].play.assert_not_called()
    mixer.voice[1].play.assert_not_called()


def test_unregistered_clip_with_stops_effect_still_raises_instead_of_stopping_silently() -> None:
    """Dropping the None guard (#804) means an unregistered clip's resolution
    failure propagates even when stops_effect=True -- it no longer falls back
    to a silent receipt.stop()."""
    output, _mixer = _make_output(AudioRegistry())
    receipt = _make_receipt()

    with pytest.raises(ValueError):
        output.handle_event(
            EffectEvent("tag", "effect", "start"),
            frozenset({"personal"}),
            _effect_oneshot_stops_effect("start", "test_pack.missing_clip"),
            receipt,
        )

    receipt.stop.assert_not_called()


def test_oserror_on_file_open_with_stops_effect_stops_receipt_immediately(tmp_path) -> None:
    """A stops_effect clip whose file fails to open must not run forever."""
    registry = AudioRegistry()
    clip_name = _register_missing_path(registry, "missing", str(tmp_path / "nonexistent.wav"))
    output, _mixer = _make_output(registry)
    receipt = _make_receipt()

    output.handle_event(
        EffectEvent("tag", "effect", "start"),
        frozenset({"personal"}),
        _effect_oneshot_stops_effect("start", clip_name),
        receipt,
    )

    receipt.stop.assert_called_once()


# ---------------------------------------------------------------------------
# handle_event — routing a valid clip into the pool reaches the hardware
# ---------------------------------------------------------------------------


def test_valid_clip_plays_on_an_idle_voice(tmp_path) -> None:
    """A registered clip is opened and played on a mixer voice at the receipt's loudness."""
    registry = AudioRegistry()
    clip_name = _register_wav(tmp_path, registry, "music")
    output, mixer = _make_output(registry, max_volume=0.4)

    output.handle_event(
        EffectEvent("rlgl", "music", "start"),
        frozenset({"ambient"}),
        _effect_loop("start", clip_name),
        _make_receipt(loudness=0.5),
    )

    mixer.voice[0].play.assert_called_once()
    assert mixer.voice[0].play.call_args[1]["loop"] is True
    assert mixer.voice[0].level == pytest.approx(0.4 * 0.5)


def test_audio_only_effect_implicitly_stops_receipt_on_finish(tmp_path) -> None:
    """An effect with no pixels/haptic implicitly sets stops_receipt=True: its

    receipt is stopped when the clip finishes naturally (audio is the whole effect)."""
    registry = AudioRegistry()
    clip_name = _register_wav(tmp_path, registry, "sting")
    output, mixer = _make_output(registry)
    receipt = _make_receipt()

    output.handle_event(
        EffectEvent("rlgl", "sting", "start"),
        frozenset({"personal"}),
        _effect_audio_only("start", clip_name),
        receipt,
    )

    mixer.voice[0].playing = False
    output.flush()

    receipt.stop.assert_called_once()


def test_clip_with_pixels_and_no_stops_effect_flag_leaves_receipt_to_rules(tmp_path) -> None:
    """An effect with pixels and no stops_effect flag leaves its receipt to rules on finish."""
    registry = AudioRegistry()
    clip_name = _register_wav(tmp_path, registry, "sting")
    output, mixer = _make_output(registry)
    receipt = _make_receipt()

    output.handle_event(
        EffectEvent("rlgl", "sting", "start"),
        frozenset({"personal"}),
        _effect_oneshot("start", clip_name),
        receipt,
    )

    mixer.voice[0].playing = False
    output.flush()

    receipt.stop.assert_not_called()


def test_clip_with_pixels_and_stops_effect_stops_receipt_on_natural_finish(tmp_path) -> None:
    """A pixels effect with stops_effect=True stops its receipt when the clip finishes."""
    registry = AudioRegistry()
    clip_name = _register_wav(tmp_path, registry, "sting")
    output, mixer = _make_output(registry)
    receipt = _make_receipt()

    output.handle_event(
        EffectEvent("rlgl", "sting", "start"),
        frozenset({"personal"}),
        _effect_oneshot_stops_effect("start", clip_name),
        receipt,
    )

    mixer.voice[0].playing = False
    output.flush()

    receipt.stop.assert_called_once()


def test_clip_with_pixels_and_stops_effect_stops_receipt_on_eviction(tmp_path) -> None:
    """A pixels effect with stops_effect=True stops its receipt when evicted by a new one-shot."""
    registry = AudioRegistry()
    clip_name = _register_wav(tmp_path, registry, "sting")
    clip_name2 = _register_wav(tmp_path, registry, "sting2")
    output, _mixer = _make_output(registry, num_voices=1)
    evicted_receipt = _make_receipt()
    evicted_receipt.is_stopped.return_value = False

    # Claim the only slot with stops_effect=True pixels effect (one-shot)
    output.handle_event(
        EffectEvent("rlgl", "sting", "start"),
        frozenset({"personal"}),
        _effect_oneshot_stops_effect("start", clip_name),
        evicted_receipt,
    )
    # A new one-shot evicts the oldest one-shot (slot 0)
    output.handle_event(
        EffectEvent("rlgl", "sting2", "start"),
        frozenset({"personal"}),
        _effect_oneshot("start", clip_name2),
        _make_receipt(),
    )

    evicted_receipt.stop.assert_called_once()


def test_clip_with_pixels_haptic_and_stops_effect_stops_receipt_on_finish(tmp_path) -> None:
    """A pixels+haptic effect with stops_effect=True stops its receipt on natural finish."""
    registry = AudioRegistry()
    clip_name = _register_wav(tmp_path, registry, "sting")
    output, mixer = _make_output(registry)
    receipt = _make_receipt()

    output.handle_event(
        EffectEvent("rlgl", "sting", "start"),
        frozenset({"personal"}),
        _effect_oneshot_with_haptic_stops_effect("start", clip_name),
        receipt,
    )

    mixer.voice[0].playing = False
    output.flush()

    receipt.stop.assert_called_once()


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
