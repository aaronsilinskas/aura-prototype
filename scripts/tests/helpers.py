"""Fakes shared by the deploy and deploy-watch tests."""

from pathlib import Path

from scripts.build import BuildError, Toolchain, VersionError


class FakeToolchain(Toolchain):
    """Writes ``FAKE_MPY:<name>`` for each compile and records every call.

    Its version check passes unless *version_mismatch* is set, and its first
    *failing_compiles* compiles raise :class:`BuildError`.
    """

    def __init__(self, *, version_mismatch: bool = False, failing_compiles: int = 0) -> None:
        self._version_mismatch = version_mismatch
        self._failing_compiles = failing_compiles
        self.checked_mounts: list[Path | None] = []
        self.compiled: list[Path] = []
        self.failed: list[Path] = []

    def compile(self, src: Path, dest: Path) -> None:
        if len(self.failed) < self._failing_compiles:
            self.failed.append(src)
            raise BuildError(f"mpy-cross failed on {src}: SyntaxError: oops")
        self.compiled.append(src)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(f"FAKE_MPY:{src.name}")

    def check_version(self, mount: Path | None) -> None:
        self.checked_mounts.append(mount)
        if self._version_mismatch:
            raise VersionError("mpy-cross major version 9 does not match CircuitPython 10.x")
