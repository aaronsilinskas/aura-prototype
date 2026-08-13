"""Tests for scripts.normalize_sounds.normalize — WAV discovery across the
distributed pack/scene sounds/ layout, and the dry-run/write/error paths.

ffmpeg calls are faked via ``unittest.mock.patch("subprocess.run")`` (matching
the pattern in test_mpy_cross_validation.py) so these tests run without ffmpeg
installed.
"""

from pathlib import Path
from unittest.mock import patch

from scripts.normalize_sounds import normalize

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _Result:
    def __init__(self, returncode: int = 0, stdout=b"", stderr=b"") -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def _fake_ffmpeg(peak_db: "float | dict[str, float]" = -6.0, fail_normalize_for=()):
    """Build a fake for ``subprocess.run`` covering every ffmpeg invocation
    ``normalize`` makes: the ``-version`` availability probe, the
    ``volumedetect`` peak measurement, and the real normalize pass.

    *peak_db* is either one value for every file or a ``{filename: peak_db}``
    map. *fail_normalize_for* names files whose normalize pass should return
    a non-zero exit code (after still writing a partial tmp file, mirroring a
    real ffmpeg crash mid-write).
    """

    def _run(args, **kwargs):
        if "-version" in args:
            return _Result(returncode=0)

        if "volumedetect" in args:
            src = Path(args[args.index("-i") + 1])
            db = peak_db.get(src.name, -6.0) if isinstance(peak_db, dict) else peak_db
            return _Result(stderr=f"[Parsed_volumedetect] max_volume: {db:+.1f} dB\n")

        # The real normalize pass -- source follows "-i", output is the last arg.
        src = Path(args[args.index("-i") + 1])
        out = Path(args[-1])
        if src.name in fail_normalize_for:
            out.write_bytes(b"PARTIAL")
            return _Result(returncode=1, stderr=b"ffmpeg exploded")
        out.write_bytes(b"NORMALIZED")
        return _Result(returncode=0)

    return _run


def _make_wav(path: Path, content: bytes = b"ORIGINAL") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


# ---------------------------------------------------------------------------
# Discovery: recurses every pack's and scene's sounds/ folder in one run
# ---------------------------------------------------------------------------


def test_normalize_finds_wav_files_across_multiple_distributed_sounds_folders(
    tmp_path: Path, capsys
) -> None:
    _make_wav(tmp_path / "packs" / "effects" / "basic" / "sounds" / "blip.wav")
    _make_wav(tmp_path / "packs" / "effects" / "elements" / "sounds" / "lightning.wav")
    _make_wav(tmp_path / "packs" / "scenes" / "tag" / "sounds" / "hit.wav")

    with patch("subprocess.run", side_effect=_fake_ffmpeg()):
        result = normalize(tmp_path, dry_run=True)

    assert result == 0
    out = capsys.readouterr().out
    assert "basic/sounds/blip.wav" in out
    assert "elements/sounds/lightning.wav" in out
    assert "tag/sounds/hit.wav" in out


def test_normalize_ignores_wav_files_outside_any_sounds_folder(tmp_path: Path, capsys) -> None:
    _make_wav(tmp_path / "packs" / "effects" / "basic" / "stray.wav")

    with patch("subprocess.run", side_effect=_fake_ffmpeg()):
        result = normalize(tmp_path, dry_run=True)

    assert result == 0
    assert "No WAV files found" in capsys.readouterr().out


def test_normalize_ignores_non_wav_files_in_a_sounds_folder(tmp_path: Path, capsys) -> None:
    sounds_dir = tmp_path / "packs" / "effects" / "basic" / "sounds"
    sounds_dir.mkdir(parents=True)
    (sounds_dir / "notes.txt").write_text("not a wav")

    with patch("subprocess.run", side_effect=_fake_ffmpeg()):
        result = normalize(tmp_path, dry_run=True)

    assert result == 0
    assert "No WAV files found" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# Directory / ffmpeg preconditions
# ---------------------------------------------------------------------------


def test_normalize_returns_error_when_root_is_not_a_directory(tmp_path: Path, capsys) -> None:
    missing = tmp_path / "does-not-exist"

    result = normalize(missing, dry_run=True)

    assert result == 1
    assert "is not a directory" in capsys.readouterr().err


def test_normalize_returns_error_when_ffmpeg_is_unavailable(tmp_path: Path, capsys) -> None:
    _make_wav(tmp_path / "packs" / "effects" / "basic" / "sounds" / "blip.wav")

    with patch("scripts.normalize_sounds._ffmpeg_available", return_value=False):
        result = normalize(tmp_path, dry_run=True)

    assert result == 1
    assert "ffmpeg not found" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# Dry run: reports measured gain, writes nothing
# ---------------------------------------------------------------------------


def test_dry_run_reports_measured_gain_without_writing(tmp_path: Path, capsys) -> None:
    wav = tmp_path / "packs" / "effects" / "basic" / "sounds" / "blip.wav"
    _make_wav(wav)

    with patch("subprocess.run", side_effect=_fake_ffmpeg(peak_db=-6.0)):
        result = normalize(tmp_path, dry_run=True)

    assert result == 0
    assert wav.read_bytes() == b"ORIGINAL"
    out = capsys.readouterr().out
    assert "[DRY RUN]" in out
    assert "peak=-6.0 dB" in out
    assert "gain=+5.9 dB" in out


# ---------------------------------------------------------------------------
# Real run: writes the normalized file in place
# ---------------------------------------------------------------------------


def test_normalize_writes_normalized_file_in_place(tmp_path: Path) -> None:
    wav = tmp_path / "packs" / "effects" / "basic" / "sounds" / "blip.wav"
    _make_wav(wav)

    with patch("subprocess.run", side_effect=_fake_ffmpeg(peak_db=-6.0)):
        result = normalize(tmp_path, dry_run=False)

    assert result == 0
    assert wav.read_bytes() == b"NORMALIZED"
    assert not wav.with_suffix(".tmp.wav").exists()


def test_normalize_reports_done_summary_on_success(tmp_path: Path, capsys) -> None:
    _make_wav(tmp_path / "packs" / "effects" / "basic" / "sounds" / "blip.wav")

    with patch("subprocess.run", side_effect=_fake_ffmpeg()):
        normalize(tmp_path, dry_run=False)

    assert "Done. 1 normalized, 0 failed." in capsys.readouterr().out


# ---------------------------------------------------------------------------
# Error paths: one file failing does not stop the others
# ---------------------------------------------------------------------------


def test_normalize_reports_error_when_peak_cannot_be_measured(tmp_path: Path, capsys) -> None:
    _make_wav(tmp_path / "packs" / "effects" / "basic" / "sounds" / "blip.wav")

    def _no_match_run(args, **kwargs):
        if "-version" in args:
            return _Result(returncode=0)
        return _Result(stderr="no volume info here")

    with patch("subprocess.run", side_effect=_no_match_run):
        result = normalize(tmp_path, dry_run=True)

    assert result == 1
    assert "could not measure peak" in capsys.readouterr().err


def test_normalize_cleans_up_tmp_file_when_ffmpeg_normalize_pass_fails(tmp_path: Path) -> None:
    wav = tmp_path / "packs" / "effects" / "basic" / "sounds" / "blip.wav"
    _make_wav(wav)

    with patch(
        "subprocess.run", side_effect=_fake_ffmpeg(peak_db=-6.0, fail_normalize_for={"blip.wav"})
    ):
        result = normalize(tmp_path, dry_run=False)

    assert result == 1
    assert wav.read_bytes() == b"ORIGINAL"
    assert not wav.with_suffix(".tmp.wav").exists()


def test_normalize_continues_past_a_failing_file_to_normalize_the_rest(
    tmp_path: Path, capsys
) -> None:
    good = tmp_path / "packs" / "effects" / "basic" / "sounds" / "good.wav"
    bad = tmp_path / "packs" / "effects" / "basic" / "sounds" / "unmeasurable.wav"
    _make_wav(good)
    _make_wav(bad)

    def _run(args, **kwargs):
        if "-version" in args:
            return _Result(returncode=0)
        if "volumedetect" in args:
            src = Path(args[args.index("-i") + 1])
            if src.name == "unmeasurable.wav":
                return _Result(stderr="no volume info")
            return _Result(stderr="[Parsed_volumedetect] max_volume: -6.0 dB\n")
        Path(args[-1]).write_bytes(b"NORMALIZED")
        return _Result(returncode=0)

    with patch("subprocess.run", side_effect=_run):
        result = normalize(tmp_path, dry_run=False)

    assert result == 1
    assert good.read_bytes() == b"NORMALIZED"
    out = capsys.readouterr().out
    assert "Done. 1 normalized, 1 failed." in out
