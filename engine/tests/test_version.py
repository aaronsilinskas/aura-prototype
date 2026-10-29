"""Tests for engine.version.Version: strict parsing and str.

Pack compatibility is checked by the catalog; see ``test_pack_catalog.py``.
"""

from __future__ import annotations

import pytest

from engine.version import Version

# ---------------------------------------------------------------------------
# parse — valid input
# ---------------------------------------------------------------------------


def test_parse_reads_major_and_minor() -> None:
    version = Version.parse("2.13")

    assert (version.major, version.minor) == (2, 13)


def test_parse_strips_surrounding_whitespace() -> None:
    version = Version.parse("  1.4\n")

    assert (version.major, version.minor) == (1, 4)


def test_parse_accepts_leading_zeros() -> None:
    version = Version.parse("01.02")

    assert (version.major, version.minor) == (1, 2)


def test_str_round_trips_parsed_version() -> None:
    assert str(Version.parse("3.7")) == "3.7"


# ---------------------------------------------------------------------------
# parse — malformed input
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "bad", ["1", "1.2.3", "one.two", "-1.0", "1 . 2", "", "\u0661.\u0662", "\u00b2.1"]
)
def test_parse_raises_value_error_naming_malformed_string(bad: str) -> None:
    with pytest.raises(ValueError) as excinfo:
        Version.parse(bad)

    assert bad in str(excinfo.value)


@pytest.mark.parametrize("bad", [1.2, None])
def test_parse_raises_value_error_naming_non_string_value(bad: object) -> None:
    with pytest.raises(ValueError) as excinfo:
        Version.parse(bad)

    assert str(bad) in str(excinfo.value)
