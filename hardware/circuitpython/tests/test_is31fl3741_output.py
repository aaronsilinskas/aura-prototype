"""Tests for IS31FL3741EffectOutput — the IS31FL3741 hardware adapter.

Geometry (cols, scope_rows) is injected at construction so the config-driven
builder can supply hardware values without hard-coded module constants.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from effects.effect import PixelBuffer
from engine.state import Scope

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
    from hardware.circuitpython.is31fl3741_output import IS31FL3741EffectOutput

    mock_matrix = MagicMock()
    return IS31FL3741EffectOutput(mock_matrix, cols=cols, scope_rows=scope_rows), mock_matrix


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------


def test_accepts_caller_supplied_cols_and_scope_rows() -> None:
    """IS31FL3741EffectOutput accepts cols and scope_rows as constructor arguments."""
    output, _ = _make_output(cols=5, scope_rows={"personal": range(0, 2)})
    assert output.min_resolution == 5


def test_registered_on_all_scopes() -> None:
    """IS31FL3741EffectOutput is registered on Scope.ALL."""
    output, _ = _make_output()
    assert Scope.ALL in output.scopes


def test_no_module_level_matrix_geometry_constants() -> None:
    """The is31fl3741_output module must not define _MATRIX_COLS or _SCOPE_ROWS."""
    import hardware.circuitpython.is31fl3741_output as mod

    assert not hasattr(mod, "_MATRIX_COLS"), "_MATRIX_COLS must not exist as a module constant"
    assert not hasattr(mod, "_SCOPE_ROWS"), "_SCOPE_ROWS must not exist as a module constant"


# ---------------------------------------------------------------------------
# Hardware routing — _write_row writes channel bytes directly to matrix buffer
# ---------------------------------------------------------------------------


def test_write_row_writes_channel_bytes_to_matrix_buffer() -> None:
    """_write_row writes R, G, B channel bytes to distinct matrix buffer positions."""
    cols = 3
    output, mock_matrix = _make_output(cols=cols, scope_rows={"personal": range(0, 1)})
    buf = PixelBuffer(cols)
    buf[0] = 0xFF0000  # R=0xFF, G=0x00, B=0x00
    buf[1] = 0x00FF00  # R=0x00, G=0xFF, B=0x00
    buf[2] = 0x0000FF  # R=0x00, G=0x00, B=0xFF

    receipt = MagicMock()
    receipt.brightness = 1.0
    output.update_pixels("personal", [buf], [receipt])

    # 3 channel bytes per pixel, all written via direct buffer indexing
    assert mock_matrix.__setitem__.call_count == cols * 3
    mock_matrix.pixel.assert_not_called()

    # Each 0xFF value appears exactly once — channels are separated correctly
    written_values = [c.args[1] for c in mock_matrix.__setitem__.call_args_list]
    assert written_values.count(0xFF) == 3
    assert written_values.count(0x00) == 6


# ---------------------------------------------------------------------------
# flush — delegates to matrix.show
# ---------------------------------------------------------------------------


def test_flush_calls_matrix_show() -> None:
    """flush() delegates to matrix.show() exactly once."""
    output, mock_matrix = _make_output()
    output.flush()
    mock_matrix.show.assert_called_once()
