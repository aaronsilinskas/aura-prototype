"""Normalize every distributed sounds/ folder to the CircuitPython audio format.

Target format: 11025 Hz, mono, 16-bit signed, peak-normalized to 0 dBFS.

Each file is measured for its peak level first, then the exact gain needed to
bring that peak to 0 dBFS is applied.  This ensures every clip plays at the
maximum possible volume without clipping.

Sounds live distributed across the tree -- one ``sounds/`` folder per effect
pack (``packs/effects/<pack>/sounds/``) and per scene
(``packs/scenes/<scene>/sounds/``) -- rather than in one shared top-level
directory. A single invocation recurses *root* to find and normalize every
``sounds/`` folder beneath it.

Usage
-----
    python scripts/normalize_sounds.py

    # Preview measured gains without writing:
    python scripts/normalize_sounds.py --dry-run

    # Normalize a different root (recurses every sounds/ folder beneath it):
    python scripts/normalize_sounds.py --root path/to/root
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
_DEFAULT_ROOT: Final = "packs"
_HEADROOM_DB: Final = 0.1  # leave a tiny margin below 0 dBFS to avoid clipping


def _ffmpeg_available() -> bool:
    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True)
        return True
    except (FileNotFoundError, subprocess.CalledProcessError):
        return False


def _find_wav_files(root: Path) -> list[Path]:
    """Return every ``*.wav`` file under any ``sounds/`` folder beneath *root*, sorted.

    Recurses the distributed pack/scene layout so one call finds every
    pack's and scene's ``sounds/`` folder, however deep *root* is.
    """
    return sorted(root.rglob("sounds/*.wav"))


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


def normalize(root: Path, dry_run: bool = False) -> int:
    """Normalize every WAV file under a sounds/ folder beneath root. Returns 0 on
    success, 1 on error."""
    if not root.is_dir():
        print(f"Error: '{root}' is not a directory.", file=sys.stderr)
        return 1

    if not _ffmpeg_available():
        print("Error: ffmpeg not found. Install it with: brew install ffmpeg", file=sys.stderr)
        return 1

    wav_files = _find_wav_files(root)
    if not wav_files:
        print(f"No WAV files found under any sounds/ folder beneath '{root}'.")
        return 0

    errors = 0
    for wav in wav_files:
        label = str(wav.relative_to(root))
        peak_db = _measure_peak_db(wav)
        if peak_db is None:
            print(f"Error: could not measure peak for {label}", file=sys.stderr)
            errors += 1
            continue

        gain_db = -peak_db - _HEADROOM_DB

        if dry_run:
            print(f"[DRY RUN] {label:40s}  peak={peak_db:+.1f} dB  gain={gain_db:+.1f} dB")
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
            print(f"Error normalizing {label}:\n{result.stderr.decode()}", file=sys.stderr)
            if tmp.exists():
                tmp.unlink()
            errors += 1
            continue

        tmp.replace(wav)
        print(f"normalized  {label:40s}  peak={peak_db:+.1f} dB  gain={gain_db:+.1f} dB")

    if not dry_run:
        print(f"Done. {len(wav_files) - errors} normalized, {errors} failed.")
    return 0 if errors == 0 else 1


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Peak-normalize every distributed sounds/ folder's WAV files to "
        "0 dBFS at 11025 Hz mono 16-bit signed."
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(_DEFAULT_ROOT),
        help=f"Root directory to recurse for sounds/ folders (default: {_DEFAULT_ROOT}).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Print measured gains without writing any files.",
    )
    args = parser.parse_args()
    sys.exit(normalize(args.root, dry_run=args.dry_run))


if __name__ == "__main__":
    main()
