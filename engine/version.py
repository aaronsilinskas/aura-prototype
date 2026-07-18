"""Version — parsed MAJOR.MINOR version with compatibility checking."""


class Version:
    """Parsed MAJOR.MINOR version.

    Construction::

        v = Version(1, 2)

    Parsing::

        v = Version.parse("1.2")

    Compatibility check::

        v.check_compatible("myrule", required_major=1, required_minor=0)
    """

    __slots__ = ("major", "minor")

    def __init__(self, major: int, minor: int) -> None:
        self.major = major
        self.minor = minor

    @staticmethod
    def parse(version_str: str) -> "Version":
        """Parse a ``'MAJOR.MINOR'`` string into a :class:`Version`."""
        parts = version_str.strip().split(".")
        return Version(int(parts[0]), int(parts[1]))

    def check_compatible(self, name: str, required_major: int, required_minor: int) -> None:
        """Raise ``ValueError`` if this version does not satisfy the minimum required.

        * Same major and ``self.minor >= required_minor`` → compatible (no-op).
        * Same major and ``self.minor < required_minor`` →
          ``ValueError`` containing "upgrade the pack".
        * Different major → ``ValueError`` containing "incompatible".
        """
        version_display = f"{self.major}.{self.minor}"
        required_display = f"{required_major}.{required_minor}"
        if self.major != required_major:
            raise ValueError(
                f"Pack '{name}' version {version_display} is incompatible with "
                + f"required {required_display}"
            )
        if self.minor < required_minor:
            raise ValueError(
                f"Pack '{name}' version {version_display} is too old; upgrade the pack "
                + f"to at least {required_display}"
            )

    def __str__(self) -> str:
        return f"{self.major}.{self.minor}"
