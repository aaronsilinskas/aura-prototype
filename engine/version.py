"""Version — a parsed MAJOR.MINOR version."""


class Version:
    """Parsed MAJOR.MINOR version.

    Build one directly or via :meth:`parse` from a string.
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

    def __str__(self) -> str:
        return f"{self.major}.{self.minor}"


def _is_ascii_digits(text: str) -> bool:
    # str.isdigit() also accepts non-ASCII digits such as "²" and "١".
    return bool(text) and all("0" <= ch <= "9" for ch in text)
