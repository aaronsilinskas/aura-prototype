"""Tests for the table-row emission helpers shared across profiler scripts.

The profiler scripts themselves run forever on-device and are not unit-tested,
but the pure logic they rely on to turn a sweep into a paste-ready
``recorded-metrics.md`` table row -- least-squares slope fitting, runtime-id
formatting, and markdown row formatting -- lives here and is.
"""

from hardware.shared.profiling_helpers import (
    board_id,
    format_runtime_id,
    format_table_row,
    linear_fit,
    print_table_row,
    runtime_id,
)


class TestLinearFit:
    def test_recovers_slope_and_intercept_of_a_clean_line(self):
        # y = 2x + 3 sampled at a few points.
        xs = [0, 1, 2, 4]
        ys = [3.0, 5.0, 7.0, 11.0]
        slope, intercept = linear_fit(xs, ys)
        assert slope == 2.0
        assert intercept == 3.0

    def test_single_point_yields_zero_slope_and_that_point_as_intercept(self):
        slope, intercept = linear_fit([5], [4.2])
        assert slope == 0.0
        assert intercept == 4.2

    def test_fits_best_line_through_noisy_points(self):
        # Points scattered around y = x: slope ~1, intercept ~0.
        xs = [0, 1, 2, 3, 4]
        ys = [0.1, 0.9, 2.1, 2.9, 4.0]
        slope, intercept = linear_fit(xs, ys)
        assert abs(slope - 1.0) < 0.05
        assert abs(intercept) < 0.1


class TestFormatRuntimeId:
    def test_joins_name_and_version_with_underscores_for_the_table_key(self):
        # Matches the recorded-metrics table key style: circuitpython_10_0_3.
        assert format_runtime_id("circuitpython", (10, 0, 3)) == "circuitpython_10_0_3"


class TestFormatTableRow:
    def test_wraps_cells_as_a_markdown_table_row(self):
        row = format_table_row(["board", "runtime", "-", "4.57%", "450"])
        assert row == "| board | runtime | - | 4.57% | 450 |"

    def test_stringifies_non_string_cells(self):
        assert format_table_row([1, 2.5]) == "| 1 | 2.5 |"

    def test_preserves_tbd_placeholder_cells(self):
        # Cells the profiler could not measure on a bare board pass through
        # verbatim so the row stays paste-ready with explicit gaps.
        row = format_table_row(["board", "_TBD_"])
        assert row == "| board | _TBD_ |"


class TestPrintTableRow:
    def test_prepends_board_runtime_driver_to_the_component_cells(self, capsys):
        print_table_row("engine_component_costs", ["0.10", "0.20", "0.30", "_TBD_"])
        out = capsys.readouterr().out
        row_line = next(line for line in out.splitlines() if line.startswith("| "))
        assert row_line == format_table_row(
            [board_id(), runtime_id(), "-", "0.10", "0.20", "0.30", "_TBD_"]
        )

    def test_uses_the_given_driver_in_place_of_the_dash(self, capsys):
        print_table_row("pixel_costs", ["1.0"], driver="neopixel_pwm")
        out = capsys.readouterr().out
        row_line = next(line for line in out.splitlines() if line.startswith("| "))
        assert " | neopixel_pwm | " in row_line

    def test_labels_the_target_table_so_the_row_is_greppable_in_serial_output(self, capsys):
        print_table_row("per_mcu_baselines", ["engine-host", "4.57%", "450"])
        out = capsys.readouterr().out
        assert "per_mcu_baselines" in out
