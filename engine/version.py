"""Version — parsed MAJOR.MINOR version with compatibility checking."""


class Version:
    """Parsed MAJOR.MINOR version.

    Build one directly, via :meth:`parse` from a string, and enforce a
    minimum with :meth:`check_compatible`.
    """

    __slots__ = ("major", "minor")

    def __init__(self, major: int, minor: int) -> None:
        self.major = major
        self.minor = minor

    @staticmethod
    def parse(version_str: object) -> "Version":
        """Parse a ``'MAJOR.MINOR'`` string into a :class:`Version`.

        Raises:
            ValueError: if ``version_str``, ignoring surrounding whitespace, is not
                a string of exactly two dot-separated ASCII-digit components.
        """
        parts = version_str.strip().split(".") if isinstance(version_str, str) else []
        if len(parts) != 2 or not all(_is_ascii_digits(part) for part in parts):
            raise ValueError(f"Malformed version {version_str!r}; expected a 'MAJOR.MINOR' string")
        return Version(int(parts[0]), int(parts[1]))

    def check_compatible(self, name: str, required_major: int, required_minor: int) -> None:
        """Raise ``ValueError`` if this version does not satisfy the minimum required.

        Compatibility requires an equal major and a minor at least
        ``required_minor``.
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


def _is_ascii_digits(text: str) -> bool:
    # str.isdigit() also accepts non-ASCII digits such as "²" and "١".
    return bool(text) and all("0" <= ch <= "9" for ch in text)
