"""Tests for IS31FL3741EffectOutput — the IS31FL3741 hardware adapter.

Geometry (cols, scope_rows) is injected at construction so the config-driven
builder can supply hardware values without hard-coded module constants.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from effects.effect import PixelBuffer
from engine.state import Scope
from hardware.circuitpython.is31fl3741_output import (
    IS31FL3741EffectOutput,
    build_offset_table,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_COLS = 13

_SCOPE_ROWS = {
    "global.buff": range(0, 1),
    "global.debuff": range(1, 2),
    "global.main": range(2, 5),
    "personal": range(5, 7),
    "directional": range(7, 8),
    "ambient": range(8, 9),
}


def _make_output(cols: int = _COLS, scope_rows: dict = _SCOPE_ROWS):
    """Build an IS31FL3741EffectOutput with a mock matrix driver."""
    mock_matrix = MagicMock()
    return IS31FL3741EffectOutput(mock_matrix, cols=cols, scope_rows=scope_rows), mock_matrix


class _RecordingMatrix:
    """Fake matrix satisfying the duck-type contract, recording every write.

    Unlike the ``MagicMock`` matrix used elsewhere, it retains each
    ``offset -> byte`` write so a test can assert exactly which register
    offset received which byte.
    """

    def __init__(self) -> None:
        self.writes: dict[int, int] = {}
        self.shown = False

    def __setitem__(self, offset: int, byte: int) -> None:
        self.writes[offset] = byte

    def show(self) -> None:
        self.shown = True


# ---------------------------------------------------------------------------
# build_offset_table — the IS31FL3741's register-addressing contract
# ---------------------------------------------------------------------------


def test_offset_table_places_red_at_the_base_register_for_a_bank0_even_column() -> None:
    """An even column below the x=10 bank split keeps R/G/B in base order."""
    table = build_offset_table([0], cols=13)

    x = 2
    b_off, g_off, r_off = table[x * 3], table[x * 3 + 1], table[x * 3 + 2]

    assert (b_off, g_off, r_off) == (8, 7, 6)


def test_offset_table_swaps_red_and_blue_registers_for_a_bank0_odd_column() -> None:
    """Column parity flips which register holds red vs. blue within bank 0."""
    table = build_offset_table([0], cols=13)

    x = 3
    b_off, g_off, r_off = table[x * 3], table[x * 3 + 1], table[x * 3 + 2]

    assert (b_off, g_off, r_off) == (10, 9, 11)


def test_offset_table_treats_column_12_like_an_odd_column() -> None:
    """Column 12 always gets the swapped register order.

    It does so regardless of its own even index — the chip's documented
    last-column exception to the parity rule.
    """
    table = build_offset_table([0], cols=13)

    x = 12
    b_off, g_off, r_off = table[x * 3], table[x * 3 + 1], table[x * 3 + 2]

    assert (b_off, g_off, r_off) == (277, 276, 278)


def test_offset_table_switches_addressing_scheme_at_the_bank_boundary() -> None:
    """Adjacent columns straddling x=10 land in unrelated register ranges.

    x=9 (bank 0) and x=10 (bank 1) use unrelated addressing formulas, so
    register offsets do not increase smoothly across the boundary the way
    they do within a bank.
    """
    table = build_offset_table([0], cols=13)

    lo = table[9 * 3], table[9 * 3 + 1], table[9 * 3 + 2]
    hi = table[10 * 3], table[10 * 3 + 1], table[10 * 3 + 2]

    assert lo == (28, 27, 29)
    assert hi == (272, 271, 270)


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------


def test_accepts_caller_supplied_cols_and_scope_rows() -> None:
    output, _ = _make_output(cols=5, scope_rows={"personal": range(0, 2)})
    assert output.min_resolution == 5


def test_registered_on_all_scopes() -> None:
    output, _ = _make_output()
    assert Scope.ALL in output.scopes


# ---------------------------------------------------------------------------
# Hardware routing — _write_row writes channel bytes directly to matrix buffer
# ---------------------------------------------------------------------------


def test_write_row_separates_rgb_channels_across_buffer_positions() -> None:
    cols = 3
    output, mock_matrix = _make_output(cols=cols, scope_rows={"personal": range(0, 1)})
    buf = PixelBuffer(cols)
    buf[0] = 0xFF0000  # R=0xFF, G=0x00, B=0x00
    buf[1] = 0x00FF00  # R=0x00, G=0xFF, B=0x00
    buf[2] = 0x0000FF  # R=0x00, G=0x00, B=0xFF

    output.update_pixels("personal", buf)

    written_values = [c.args[1] for c in mock_matrix.__setitem__.call_args_list]
    assert written_values.count(0xFF) == 3
    assert written_values.count(0x00) == 6


def test_write_row_does_not_use_pixel_api() -> None:
    output, mock_matrix = _make_output(cols=2, scope_rows={"personal": range(0, 1)})
    buf = PixelBuffer(2)

    output.update_pixels("personal", buf)

    mock_matrix.pixel.assert_not_called()


def test_write_row_writes_each_channel_to_a_distinct_buffer_position() -> None:
    cols = 2
    output, mock_matrix = _make_output(cols=cols, scope_rows={"personal": range(0, 1)})
    buf = PixelBuffer(cols)
    buf[0] = 0xFF0000  # R=0xFF, G=0x00, B=0x00

    output.update_pixels("personal", buf)

    written = {c.args[0]: c.args[1] for c in mock_matrix.__setitem__.call_args_list}
    assert len(written) == cols * 3
    assert 0xFF in written.values()


def test_write_row_routes_red_byte_to_the_b_off_register_and_blue_to_r_off() -> None:
    """Document the actual channel mapping, which does not match register names.

    Logical row 0 maps to physical driver row 8 (``IS31FL3741EffectOutput._rowmap``),
    and column 0 there computes to registers ``(b_off, g_off, r_off) = (242, 241,
    240)``. The write puts the pixel's red byte in the register the constructor
    names ``b_off``, and its blue byte in the register named ``r_off`` — only
    green lands where its name suggests.
    """
    matrix = _RecordingMatrix()
    output = IS31FL3741EffectOutput(matrix, cols=1, scope_rows={"personal": range(0, 1)})
    buf = PixelBuffer(1)
    buf[0] = 0xAABBCC  # R=0xAA, G=0xBB, B=0xCC

    output.update_pixels("personal", buf)

    assert matrix.writes[242] == 0xAA  # b_off
    assert matrix.writes[241] == 0xBB  # g_off
    assert matrix.writes[240] == 0xCC  # r_off


# ---------------------------------------------------------------------------
# flush — delegates to matrix.show
# ---------------------------------------------------------------------------


def test_flush_calls_matrix_show() -> None:
    output, mock_matrix = _make_output()
    output.flush()
    mock_matrix.show.assert_called_once()
