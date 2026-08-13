import os

import engine._path as _path


def scan_sound_dir(path: str) -> dict[str, str]:
    """Return a stem → WAV path map for every ``*.wav`` file directly in *path*.

    Mirrors ``scan_item_names``'s (``engine.packs``) stem-is-the-name rule, but for
    audio clips instead of pack items.  A missing or non-directory *path* yields an
    empty map rather than raising — callers with no wrapping ``scan_dir`` to guard
    the check (unlike ``scan_item_names``, whose callers check first) can call this
    directly.
    """
    sounds: dict[str, str] = {}
    if not _path.isdir(path):
        return sounds
    for fname in os.listdir(path):
        if not fname.endswith(".wav"):
            continue
        full_path = _path.join(path, fname)
        if _path.isdir(full_path):
            continue
        stem = fname[:-4]
        sounds[stem] = full_path
    return sounds


class AudioRegistry:
    """Maps clip names to WAV file paths.

    Pack authors (or setup code) call ``register`` explicitly; consumers
    call ``path`` to resolve a name to a WAV path at runtime.

    Has no dependency on ``PackRegistry`` or any pack directory layout.
    """

    __slots__ = ["_clips"]

    def __init__(self) -> None:
        self._clips: dict[str, str] = {}

    def register(self, name: str, path: str) -> None:
        """Store a clip name → WAV path mapping, overwriting any previous entry."""
        self._clips[name] = path

    def path(self, name: str) -> str | None:
        """Return the WAV path for *name*, or ``None`` if not registered."""
        return self._clips.get(name)
