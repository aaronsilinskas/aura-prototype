"""Tests for AudioEffectOutput — the live VoiceSink adapter.

Voice-slot bookkeeping (claim/eviction/sweep, the stops-receipt release rule,
loudness tracking) and the ``clip_stops_receipt`` claim rule live in
``hardware/shared/voice_pool.py`` and are covered by ``test_voice_pool.py``.
These tests cover only what the adapter itself owns: the shell-routing guards in
``handle_event``, that it feeds the claim rule's answer into the pool, and the
last-mile hardware mapping of the five ``VoiceSink`` methods onto the mixer and
file handles.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from effects.effect import AudioPlaybackConfig, Effect, EffectPixels, ResolvedClip
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


def _make_output(max_volume: float = 0.2, num_voices: int = 2) -> tuple[object, MagicMock]:
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
        max_volume=max_volume,
        num_voices=num_voices,
        i2s_bit_clock=_FAKE_BIT_CLOCK,
        i2s_word_select=_FAKE_WORD_SELECT,
        i2s_data=_FAKE_DATA,
    )
    return output, mock_mixer


def _with_pixels() -> Effect:
    """An effect with pixels, so a clip's release leaves the receipt to rules."""
    return Effect(name="test", pixels=MagicMock(spec=EffectPixels))


def _audio_only() -> Effect:
    """An effect with no pixels or haptic: audio is the whole effect."""
    return Effect(name="audio_only")


def _event(path: str, loop: bool = False, stops_effect: bool = False) -> EffectEvent:
    """A start event carrying a clip resolved to *path*."""
    config = AudioPlaybackConfig(name="sfx.clip", loop=loop, stops_effect=stops_effect)
    return EffectEvent("sfx", "effect", "start", ResolvedClip(config, path))


def _wav(tmp_path, name: str = "clip") -> str:
    wav = tmp_path / f"{name}.wav"
    wav.write_bytes(b"RIFF")
    return str(wav)


# ---------------------------------------------------------------------------
# Constructor
# ---------------------------------------------------------------------------


def test_i2sout_constructed_with_caller_supplied_pins() -> None:
    """audiobusio.I2SOut is constructed with the caller-supplied I2S pins."""
    import audiobusio  # type: ignore[import]

    _make_output()

    audiobusio.I2SOut.assert_called_once_with(_FAKE_BIT_CLOCK, _FAKE_WORD_SELECT, _FAKE_DATA)


def test_mixer_constructed_with_num_voices() -> None:
    """audiomixer.Mixer is constructed with voice_count=num_voices."""
    import audiomixer  # type: ignore[import]

    _make_output(num_voices=4)

    audiomixer.Mixer.assert_called_once()
    assert audiomixer.Mixer.call_args[1]["voice_count"] == 4


# ---------------------------------------------------------------------------
# handle_event — events with no playable clip
# ---------------------------------------------------------------------------


def test_an_event_with_no_clip_plays_nothing() -> None:
    output, mixer = _make_output()

    output.handle_event(
        EffectEvent("rlgl", "effect", "stop"),
        frozenset({"personal"}),
        _with_pixels(),
        _make_receipt(),
    )

    mixer.voice[0].play.assert_not_called()
    mixer.voice[1].play.assert_not_called()


def test_a_clip_whose_file_cannot_be_opened_plays_nothing(tmp_path) -> None:
    output, mixer = _make_output()

    output.handle_event(
        _event(str(tmp_path / "nonexistent.wav")),
        frozenset({"personal"}),
        _with_pixels(),
        _make_receipt(),
    )

    mixer.voice[0].play.assert_not_called()
    mixer.voice[1].play.assert_not_called()


def test_a_stops_effect_clip_whose_file_cannot_be_opened_stops_the_receipt(tmp_path) -> None:
    """A stops_effect clip whose file fails to open must not run forever."""
    output, _mixer = _make_output()
    receipt = _make_receipt()

    output.handle_event(
        _event(str(tmp_path / "nonexistent.wav"), stops_effect=True),
        frozenset({"personal"}),
        _with_pixels(),
        receipt,
    )

    receipt.stop.assert_called_once()


# ---------------------------------------------------------------------------
# handle_event — playing the resolved clip's path
# ---------------------------------------------------------------------------


def test_the_resolved_clips_path_plays_on_an_idle_voice(tmp_path) -> None:
    """The file at the event's resolved path is opened and played at the receipt's loudness."""
    import audiocore  # type: ignore[import]

    output, mixer = _make_output(max_volume=0.4)
    path = _wav(tmp_path, "music")

    output.handle_event(
        _event(path, loop=True),
        frozenset({"ambient"}),
        _with_pixels(),
        _make_receipt(loudness=0.5),
    )

    opened_file = audiocore.WaveFile.call_args[0][0]
    assert opened_file.name == path
    mixer.voice[0].play.assert_called_once()
    assert mixer.voice[0].play.call_args[1]["loop"] is True
    assert mixer.voice[0].level == pytest.approx(0.2)
    output.stop(0)


def test_a_finished_stops_effect_clip_stops_the_receipt(tmp_path) -> None:
    """stops_effect is read from the event's resolved clip."""
    output, mixer = _make_output()
    receipt = _make_receipt()

    output.handle_event(
        _event(_wav(tmp_path), stops_effect=True), frozenset({"personal"}), _with_pixels(), receipt
    )
    mixer.voice[0].playing = False
    output.flush()

    receipt.stop.assert_called_once()


def test_a_finished_clip_on_an_audio_only_effect_stops_the_receipt(tmp_path) -> None:
    """With no pixels or haptic, audio is the whole effect, so its end ends the receipt."""
    output, mixer = _make_output()
    receipt = _make_receipt()

    output.handle_event(_event(_wav(tmp_path)), frozenset({"personal"}), _audio_only(), receipt)
    mixer.voice[0].playing = False
    output.flush()

    receipt.stop.assert_called_once()


def test_a_finished_clip_with_pixels_and_no_stops_effect_leaves_the_receipt_to_rules(
    tmp_path,
) -> None:
    output, mixer = _make_output()
    receipt = _make_receipt()

    output.handle_event(_event(_wav(tmp_path)), frozenset({"personal"}), _with_pixels(), receipt)
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
    output, _ = _make_output()

    source = output.open_source(str(wav))

    f, wave = source
    audiocore.WaveFile.assert_called_once_with(f)
    assert wave is audiocore.WaveFile.return_value
    assert not f.closed  # file stays open while playing
    f.close()


def test_open_source_returns_none_on_oserror(tmp_path) -> None:
    """open_source returns None when the file cannot be opened."""
    output, _ = _make_output()

    assert output.open_source(str(tmp_path / "nope.wav")) is None


def test_play_stores_source_and_plays_wave_with_loop(tmp_path) -> None:
    """play hands the WaveFile to the slot's voice with the loop flag."""
    wav = tmp_path / "clip.wav"
    wav.write_bytes(b"RIFF")
    output, mixer = _make_output()
    source = output.open_source(str(wav))
    _, wave = source

    output.play(1, source, loop=True)

    mixer.voice[1].play.assert_called_once_with(wave, loop=True)
    output.stop(1)  # cleanup: close the file


def test_stop_stops_voice_and_closes_file(tmp_path) -> None:
    """stop stops the slot's voice and closes the open WAV file."""
    wav = tmp_path / "clip.wav"
    wav.write_bytes(b"RIFF")
    output, mixer = _make_output()
    source = output.open_source(str(wav))
    f, _ = source
    output.play(0, source, loop=False)

    output.stop(0)

    mixer.voice[0].stop.assert_called_once()
    assert f.closed


def test_stop_on_idle_slot_stops_voice_without_error(tmp_path) -> None:
    """stop on a slot with no open source still stops the voice and does not raise."""
    output, mixer = _make_output()

    output.stop(0)

    mixer.voice[0].stop.assert_called_once()


def test_set_loudness_applies_max_volume(tmp_path) -> None:
    """set_loudness sets the voice level to max_volume * loudness."""
    output, mixer = _make_output(max_volume=0.4)

    output.set_loudness(0, 0.5)

    assert mixer.voice[0].level == pytest.approx(0.2)


def test_is_playing_reads_voice_playing(tmp_path) -> None:
    """is_playing reports the slot voice's playing flag."""
    output, mixer = _make_output()

    mixer.voice[0].playing = True
    mixer.voice[1].playing = False

    assert output.is_playing(0) is True
    assert output.is_playing(1) is False
