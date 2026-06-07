"""Normalize all WAV files in the sounds/ directory to the CircuitPython audio format.

Target format: 11025 Hz, mono, 16-bit signed, peak-normalized to 0 dBFS.

Each file is measured for its peak level first, then the exact gain needed to
bring that peak to 0 dBFS is applied.  This ensures every clip plays at the
maximum possible volume without clipping.

Usage
-----
    python scripts/normalize_sounds.py

    # Preview measured gains without writing:
    python scripts/normalize_sounds.py --dry-run

    # Normalize a different directory:
    python scripts/normalize_sounds.py --sounds-dir path/to/sounds
"""

import argparse
import re
import subprocess
import sys
from pathlib import Path

try:
    from typing import Final
except ImportError:
    pass

_SAMPLE_RATE: Final = 11025
_CHANNELS: Final = 1
_SAMPLE_FMT: Final = "s16"
_DEFAULT_SOUNDS_DIR: Final = "sounds"
_HEADROOM_DB: Final = 0.1  # leave a tiny margin below 0 dBFS to avoid clipping


def _ffmpeg_available() -> bool:
    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True)
        return True
    except (FileNotFoundError, subprocess.CalledProcessError):
        return False


def _measure_peak_db(wav: Path) -> float | None:
    """Return the peak level of wav in dBFS, or None on failure.

    Runs ffmpeg volumedetect and parses 'max_volume: -X.X dB' from stderr.
    """
    result = subprocess.run(
        ["ffmpeg", "-i", str(wav), "-af", "volumedetect", "-f", "null", "/dev/null"],
        capture_output=True,
        text=True,
    )
    match = re.search(r"max_volume: (-?[\d.]+) dB", result.stderr)
    if match is None:
        return None
    return float(match.group(1))


def normalize(sounds_dir: Path, dry_run: bool = False) -> int:
    """Normalize all WAV files in sounds_dir. Returns 0 on success, 1 on error."""
    if not sounds_dir.is_dir():
        print(f"Error: '{sounds_dir}' is not a directory.", file=sys.stderr)
        return 1

    if not _ffmpeg_available():
        print("Error: ffmpeg not found. Install it with: brew install ffmpeg", file=sys.stderr)
        return 1

    wav_files = sorted(sounds_dir.glob("*.wav"))
    if not wav_files:
        print(f"No WAV files found in '{sounds_dir}'.")
        return 0

    errors = 0
    for wav in wav_files:
        peak_db = _measure_peak_db(wav)
        if peak_db is None:
            print(f"Error: could not measure peak for {wav.name}", file=sys.stderr)
            errors += 1
            continue

        gain_db = -peak_db - _HEADROOM_DB

        if dry_run:
            print(f"[DRY RUN] {wav.name:30s}  peak={peak_db:+.1f} dB  gain={gain_db:+.1f} dB")
            continue

        tmp = wav.with_suffix(".tmp.wav")
        result = subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-i",
                str(wav),
                "-af",
                f"volume={gain_db}dB",
                "-ar",
                str(_SAMPLE_RATE),
                "-ac",
                str(_CHANNELS),
                "-sample_fmt",
                _SAMPLE_FMT,
                str(tmp),
            ],
            capture_output=True,
        )
        if result.returncode != 0:
            print(f"Error normalizing {wav.name}:\n{result.stderr.decode()}", file=sys.stderr)
            if tmp.exists():
                tmp.unlink()
            errors += 1
            continue

        tmp.replace(wav)
        print(f"normalized  {wav.name:30s}  peak={peak_db:+.1f} dB  gain={gain_db:+.1f} dB")

    if not dry_run:
        print(f"Done. {len(wav_files) - errors} normalized, {errors} failed.")
    return 0 if errors == 0 else 1


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Peak-normalize WAV files to 0 dBFS at 11025 Hz mono 16-bit signed."
    )
    parser.add_argument(
        "--sounds-dir",
        type=Path,
        default=Path(_DEFAULT_SOUNDS_DIR),
        help=f"Directory containing WAV files to normalize (default: {_DEFAULT_SOUNDS_DIR}).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Print measured gains without writing any files.",
    )
    args = parser.parse_args()
    sys.exit(normalize(args.sounds_dir, dry_run=args.dry_run))


if __name__ == "__main__":
    main()
