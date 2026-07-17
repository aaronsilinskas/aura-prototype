"""Tests for the table-row emission helpers shared across profiler scripts.

The profiler scripts themselves run forever on-device and are not unit-tested,
but the pure logic they rely on to turn a sweep into a paste-ready
``recorded-metrics.md`` table row -- least-squares slope fitting, runtime-id
formatting, markdown row formatting, and the scene-load profiler's harness
label -- lives here and is.
"""

from hardware.shared.device_config import parse_device_config
from hardware.shared.profiling_helpers import (
    board_id,
    format_runtime_id,
    format_table_row,
    linear_fit,
    metrics_harness_label,
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


class TestMetricsHarnessLabel:
    def test_full_harness_joins_all_five_parts_with_plus(self):
        # The sample IS31FL3741 matrix: 13 cols x 9 scoped rows = 117px.
        config = parse_device_config(
            {
                "pixels": [
                    {
                        "type": "matrix",
                        "cols": 13,
                        "scope_rows": {
                            "global.buff": [0, 1],
                            "global.debuff": [1, 2],
                            "global.main": [2, 5],
                            "personal": [5, 7],
                            "directional": [7, 8],
                            "ambient": [8, 9],
                        },
                    }
                ],
                "audio": {
                    "voices": 4,
                    "clips": {},
                    "i2s_bit_clock": "GP10",
                    "i2s_word_select": "GP11",
                    "i2s_data": "GP12",
                },
                "haptics": {},
                "accelerometer": {},
                "ir": {"rx": "D11"},
            }
        )

        label = metrics_harness_label(config)

        assert label == "matrix(117px)+audio(v4)+haptic+accel+ir(rx1)"

    def test_declared_but_disabled_audio_section_reports_no_audio(self):
        config = parse_device_config(
            {
                "audio": {
                    "enabled": False,
                    "voices": 4,
                    "clips": {},
                    "i2s_bit_clock": "GP10",
                    "i2s_word_select": "GP11",
                    "i2s_data": "GP12",
                }
            }
        )

        label = metrics_harness_label(config)

        assert "+no-audio+" in label

    def test_disabling_audio_swaps_in_no_audio_leaving_other_parts_unchanged(self):
        config = parse_device_config(
            {
                "pixels": [
                    {
                        "type": "matrix",
                        "cols": 13,
                        "scope_rows": {
                            "global.buff": [0, 1],
                            "global.debuff": [1, 2],
                            "global.main": [2, 5],
                            "personal": [5, 7],
                            "directional": [7, 8],
                            "ambient": [8, 9],
                        },
                    }
                ],
                "haptics": {},
                "ir": {"rx": "D11"},
            }
        )

        label = metrics_harness_label(config)

        assert label == "matrix(117px)+no-audio+haptic+no-accel+ir(rx1)"

    def test_matrix_pixel_count_is_cols_times_rows_covered_by_scope_rows(self):
        # A narrower 8x4 matrix using only two of the six scopes: 8 x 4 = 32.
        config = parse_device_config(
            {
                "pixels": [
                    {
                        "type": "matrix",
                        "cols": 8,
                        "scope_rows": {
                            "global.main": [0, 3],
                            "personal": [3, 4],
                        },
                    }
                ]
            }
        )

        label = metrics_harness_label(config)

        assert label.startswith("matrix(32px)+")

    def test_matrix_wins_the_pixels_label_when_pixels_mixes_matrix_and_neopixel(self):
        # Real props never mix the two, but the label still must pick one
        # deterministically if a config does.
        config = parse_device_config(
            {
                "pixels": [
                    {
                        "type": "matrix",
                        "cols": 8,
                        "scope_rows": {"personal": [0, 4]},
                    },
                    {
                        "type": "neopixel",
                        "pin": "D5",
                        "count": 30,
                        "scope_pixels": {"ambient": [0, 30]},
                    },
                ]
            }
        )

        label = metrics_harness_label(config)

        assert label.startswith("matrix(32px)+")

    def test_disabled_matrix_does_not_shadow_an_enabled_neopixel_entry(self):
        # A disabled matrix did not get built, so a co-declared enabled
        # NeoPixel entry -- not the matrix -- decides the label.
        config = parse_device_config(
            {
                "pixels": [
                    {
                        "type": "matrix",
                        "cols": 13,
                        "scope_rows": {"personal": [0, 9]},
                        "enabled": False,
                    },
                    {
                        "type": "neopixel",
                        "pin": "D5",
                        "count": 30,
                        "scope_pixels": {"ambient": [0, 30]},
                    },
                ]
            }
        )

        label = metrics_harness_label(config)

        assert label.startswith("neopixel(30px)+")

    def test_neopixel_pixel_count_sums_counts_across_multiple_strip_entries(self):
        config = parse_device_config(
            {
                "pixels": [
                    {
                        "type": "neopixel",
                        "pin": "D5",
                        "count": 30,
                        "scope_pixels": {"personal": [0, 30]},
                    },
                    {
                        "type": "neopixel",
                        "pin": "D6",
                        "count": 10,
                        "scope_pixels": {"ambient": [0, 10]},
                    },
                ]
            }
        )

        label = metrics_harness_label(config)

        assert label.startswith("neopixel(40px)+")

    def test_disabled_neopixel_entry_does_not_inflate_the_pixel_count(self):
        config = parse_device_config(
            {
                "pixels": [
                    {
                        "type": "neopixel",
                        "pin": "D5",
                        "count": 30,
                        "scope_pixels": {"personal": [0, 30]},
                    },
                    {
                        "type": "neopixel",
                        "pin": "D6",
                        "count": 10,
                        "scope_pixels": {"ambient": [0, 10]},
                        "enabled": False,
                    },
                ]
            }
        )

        label = metrics_harness_label(config)

        assert label.startswith("neopixel(30px)+")

    def test_neopixel_pixel_count_sums_counts_across_legacy_scope_entries(self):
        config = parse_device_config(
            {
                "pixels": [
                    {
                        "type": "neopixel",
                        "scopes": {
                            "personal": {"pin": "D5", "count": 30},
                            "ambient": {"pin": "D6", "count": 10},
                        },
                    }
                ]
            }
        )

        label = metrics_harness_label(config)

        assert label.startswith("neopixel(40px)+")

    def test_no_pixels_label_when_pixels_list_is_empty(self):
        config = parse_device_config({})

        label = metrics_harness_label(config)

        assert label.startswith("no-pixels+")

    def test_declared_but_disabled_matrix_reports_no_pixels(self):
        # A matrix present but not enabled did not get built -- it must
        # label identically to no pixels section at all.
        config = parse_device_config(
            {
                "pixels": [
                    {
                        "type": "matrix",
                        "cols": 13,
                        "scope_rows": {"personal": [0, 9]},
                        "enabled": False,
                    }
                ]
            }
        )

        label = metrics_harness_label(config)

        assert label.startswith("no-pixels+")

    def test_all_disabled_pixels_list_reports_no_pixels(self):
        config = parse_device_config(
            {
                "pixels": [
                    {
                        "type": "neopixel",
                        "pin": "D5",
                        "count": 30,
                        "scope_pixels": {"personal": [0, 30]},
                        "enabled": False,
                    },
                    {
                        "type": "neopixel",
                        "pin": "D6",
                        "count": 10,
                        "scope_pixels": {"ambient": [0, 10]},
                        "enabled": False,
                    },
                ]
            }
        )

        label = metrics_harness_label(config)

        assert label.startswith("no-pixels+")

    def test_ir_part_reports_receiver_count_for_a_single_pin_rx(self):
        config = parse_device_config({"ir": {"rx": "D11"}})

        label = metrics_harness_label(config)

        assert label.endswith("+ir(rx1)")

    def test_ir_part_reports_receiver_count_for_a_multi_pin_rx(self):
        config = parse_device_config({"ir": {"rx": ["D11", "D12", "D13"]}})

        label = metrics_harness_label(config)

        assert label.endswith("+ir(rx3)")

    def test_no_ir_label_when_ir_section_is_absent(self):
        config = parse_device_config({})

        label = metrics_harness_label(config)

        assert label.endswith("+no-ir")

    def test_declared_but_disabled_ir_section_reports_no_ir(self):
        config = parse_device_config({"ir": {"rx": "D11", "enabled": False}})

        label = metrics_harness_label(config)

        assert label.endswith("+no-ir")

    def test_declared_haptics_section_reports_haptic(self):
        config = parse_device_config({"haptics": {}})

        label = metrics_harness_label(config)

        assert "+haptic+" in label

    def test_absent_haptics_section_reports_no_haptic(self):
        config = parse_device_config({})

        label = metrics_harness_label(config)

        assert "+no-haptic+" in label

    def test_declared_but_disabled_haptics_section_reports_no_haptic(self):
        # A declared-and-disabled section must label identically to an
        # absent one -- the label describes what ran, not why it didn't.
        config = parse_device_config({"haptics": {"enabled": False}})

        label = metrics_harness_label(config)

        assert "+no-haptic+" in label

    def test_declared_accelerometer_section_reports_accel(self):
        config = parse_device_config({"accelerometer": {}})

        label = metrics_harness_label(config)

        assert "+accel+" in label

    def test_absent_accelerometer_section_reports_no_accel(self):
        config = parse_device_config({})

        label = metrics_harness_label(config)

        assert "+no-accel+" in label

    def test_declared_but_disabled_accelerometer_section_reports_no_accel(self):
        config = parse_device_config({"accelerometer": {"enabled": False}})

        label = metrics_harness_label(config)

        assert "+no-accel+" in label
