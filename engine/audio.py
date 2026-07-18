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
