import pytest

from effects.effect import PixelBuffer
from hardware.shared.matrix_output import MatrixEffectOutput

# ---------------------------------------------------------------------------
# Test double — concrete subclass with spy on _write_row
# ---------------------------------------------------------------------------


class SpyMatrixOutput(MatrixEffectOutput):
    """Concrete subclass that records every _write_row call for assertion."""

    def __init__(self, cols: int, scope_rows: dict) -> None:
        super().__init__(cols, scope_rows)
        self.scopes = []
        self.write_row_calls: list = []

    def _write_row(self, row: int, pixels: PixelBuffer) -> None:
        self.write_row_calls.append((row, pixels))


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_SCOPE_ROWS = {
    "global.buff": range(0, 1),
    "global.debuff": range(1, 2),
    "global.main": range(2, 5),
    "personal": range(5, 7),
    "directional": range(7, 9),
}
_COLS = 8


@pytest.fixture()
def output() -> SpyMatrixOutput:
    return SpyMatrixOutput(cols=_COLS, scope_rows=_SCOPE_ROWS)


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------


def test_min_resolution_equals_cols(output: SpyMatrixOutput) -> None:
    assert output.min_resolution == _COLS


def test_create_buffer_returns_pixel_buffer_sized_to_cols(output: SpyMatrixOutput) -> None:
    buf = output.create_buffer("global.main")
    assert len(buf) == _COLS


def test_create_buffer_returns_new_instance_each_call(output: SpyMatrixOutput) -> None:
    buf_a = output.create_buffer("personal")
    buf_b = output.create_buffer("personal")
    assert buf_a is not buf_b


# ---------------------------------------------------------------------------
# update_pixels — row band routing
# ---------------------------------------------------------------------------


def test_update_pixels_routes_buffer_to_every_row_in_scope_band(output: SpyMatrixOutput) -> None:
    buf = PixelBuffer(_COLS)
    output.update_pixels("global.main", buf)
    rows_written = [r for r, _ in output.write_row_calls]
    assert rows_written == [2, 3, 4]


def test_update_pixels_single_row_band(output: SpyMatrixOutput) -> None:
    buf = PixelBuffer(_COLS)
    output.update_pixels("global.buff", buf)
    rows_written = [r for r, _ in output.write_row_calls]
    assert rows_written == [0]


@pytest.mark.parametrize(
    ("scope_key", "expected_rows"),
    [
        ("global.buff", [0]),
        ("global.debuff", [1]),
        ("global.main", [2, 3, 4]),
        ("personal", [5, 6]),
        ("directional", [7, 8]),
    ],
)
def test_update_pixels_routes_correct_band_for_each_scope_key(
    output: SpyMatrixOutput, scope_key: str, expected_rows: list[int]
) -> None:
    buf = PixelBuffer(_COLS)
    output.update_pixels(scope_key, buf)
    assert [r for r, _ in output.write_row_calls] == expected_rows


def test_update_pixels_writes_the_same_buffer_verbatim_to_every_row(
    output: SpyMatrixOutput,
) -> None:
    buf = PixelBuffer(_COLS)
    buf[0] = 0xFF0000
    output.update_pixels("personal", buf)
    for _, pixels in output.write_row_calls:
        assert pixels is buf


# ---------------------------------------------------------------------------
# clear_pixels — zeros the row band
# ---------------------------------------------------------------------------


def test_clear_pixels_zeros_every_row_in_scope_band(output: SpyMatrixOutput) -> None:
    output.clear_pixels("global.main")
    rows_written = [r for r, _ in output.write_row_calls]
    assert rows_written == [2, 3, 4]


def test_clear_pixels_writes_zeros(output: SpyMatrixOutput) -> None:
    output.clear_pixels("personal")
    for _, pixels in output.write_row_calls:
        assert all(c == 0 for c in pixels)


def test_clear_pixels_writes_zeros_regardless_of_prior_state(output: SpyMatrixOutput) -> None:
    buf = PixelBuffer(_COLS)
    buf[0] = 0xFF0000
    output.update_pixels("personal", buf)
    output.write_row_calls.clear()
    output.clear_pixels("personal")
    for _, pixels in output.write_row_calls:
        assert all(c == 0 for c in pixels)


# ---------------------------------------------------------------------------
# _write_row is abstract
# ---------------------------------------------------------------------------


def test_write_row_raises_not_implemented() -> None:
    base = MatrixEffectOutput(cols=4, scope_rows={"key": range(0, 1)})
    with pytest.raises(NotImplementedError):
        base._write_row(0, PixelBuffer(4))
