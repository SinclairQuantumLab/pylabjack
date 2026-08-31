import inspect

import pytest

from pylabjack import LabJackDeviceTypeEnum
import pylabjack._stream as stream_module
from pylabjack._stream import _resolve_stream_settling_advice
from pylabjack.labjack_device import _format_tagged_message


def _resolve_t7(
    *,
    scan_channels=("AIN0", "AIN2"),
    input_range_v=1.0,
    resolution_index=1,
    settling_us=0.0,
):
    return _resolve_stream_settling_advice(
        device_type=LabJackDeviceTypeEnum.T7,
        scan_channels=scan_channels,
        input_range_v=input_range_v,
        resolution_index=resolution_index,
        settling_us=settling_us,
    )


def test_tagged_message_indents_continuation_lines_by_prefix_width():
    assert (
        _format_tagged_message("INFO", "first line\nsecond line")
        == "INFO: first line\n      second line"
    )
    assert _format_tagged_message("WARNING:", "one line") == "WARNING: one line"


@pytest.mark.parametrize("tag", ["", "  ", "INFO\nWARNING"])
def test_tagged_message_rejects_invalid_tags(tag):
    with pytest.raises(ValueError, match="single-line"):
        _format_tagged_message(tag, "message")


def test_resolver_has_no_source_resistance_input():
    assert tuple(inspect.signature(_resolve_stream_settling_advice).parameters) == (
        "device_type",
        "scan_channels",
        "input_range_v",
        "resolution_index",
        "settling_us",
    )


def test_t7_table_1_values_are_transcribed_exactly():
    assert stream_module._T7_AUTO_SETTLING_US == {
        1: {1: 10.0, 4: 10.0, 8: 10.0},
        10: {1: 200.0, 4: 500.0, 8: 2_000.0},
        100: {1: 1_000.0, 4: 5_000.0, 8: 10_000.0},
        1000: {1: 5_000.0, 4: 5_000.0, 8: 10_000.0},
    }


def test_t7_table_2_values_are_transcribed_exactly():
    auto = stream_module._AUTO
    out_of_spec = stream_module._OUT_OF_SPEC
    assert stream_module._T7_SOURCE_RESISTANCE_SETTLING == {
        1: {
            1: (auto, auto, 100.0, 5_000.0),
            4: (auto, auto, 500.0, 250_000.0),
            8: (auto, auto, auto, out_of_spec),
        },
        10: {
            1: (auto, 1_000.0, 5_000.0, out_of_spec),
            4: (auto, auto, 10_000.0, 1_000_000.0),
            8: (auto, auto, out_of_spec, out_of_spec),
        },
        100: {
            1: (auto, out_of_spec, out_of_spec, out_of_spec),
            4: (auto, out_of_spec, out_of_spec, out_of_spec),
            8: (auto, out_of_spec, out_of_spec, out_of_spec),
        },
        1000: {
            1: (auto, out_of_spec, out_of_spec, out_of_spec),
            4: (auto, out_of_spec, out_of_spec, out_of_spec),
            8: (auto, out_of_spec, out_of_spec, out_of_spec),
        },
    }


def test_t7_gain_10_ri_1_auto_advice_matches_published_table_points():
    advice = _resolve_t7()

    assert advice is not None
    assert advice.tag == "INFO"
    assert advice.message == (
        "STREAM_SETTLING_US value (currently Auto (200 µs)) may need to be "
        "increased depending on source resistance; 10 kΩ: suggested ≥ 1 ms; 100 kΩ: "
        "suggested ≥ 5 ms; 1 MΩ: 1 s failed absolute accuracy."
    )
    assert "\n" not in advice.message


def test_manual_value_below_auto_is_a_warning():
    advice = _resolve_t7(settling_us=100.0)

    assert advice is not None
    assert advice.tag == "WARNING"
    assert advice.message.startswith(
        "STREAM_SETTLING_US value (currently 100 µs) is below T7 Table 1 "
        "Auto (200 µs)"
    )
    assert "1 kΩ: suggested ≥ 200 µs" in advice.message
    assert "10 kΩ: suggested ≥ 1 ms" in advice.message
    assert "100 kΩ: suggested ≥ 5 ms" in advice.message
    assert advice.message.endswith("1 MΩ: 1 s failed absolute accuracy.")


def test_manual_value_omits_numeric_points_it_already_satisfies():
    advice = _resolve_t7(settling_us=1_000.0)

    assert advice is not None
    assert advice.tag == "INFO"
    assert "1 kΩ:" not in advice.message
    assert "10 kΩ:" not in advice.message
    assert "100 kΩ: suggested ≥ 5 ms" in advice.message
    assert "1 MΩ: 1 s failed absolute accuracy" in advice.message


def test_value_covering_all_table_points_avoids_may_need_wording():
    advice = _resolve_t7(
        input_range_v=10.0,
        resolution_index=1,
        settling_us=5_000.0,
    )

    assert advice is not None
    assert advice.message == (
        "STREAM_SETTLING_US value (currently 5 ms); T7 Table 2 suggests no "
        "increase through 1 MΩ."
    )


def test_long_table_value_marks_software_settling_requirement():
    advice = _resolve_t7(
        input_range_v=10.0,
        resolution_index=4,
    )

    assert advice is not None
    assert (
        "1 MΩ: suggested ≥ 250 ms (software settling required)"
        in advice.message
    )


def test_unpublished_resolution_row_is_not_interpolated():
    advice = _resolve_t7(resolution_index=2)

    assert advice is not None
    assert advice.tag == "INFO"
    assert (
        "no exact T7 Tables 1-2 source-resistance row for gain 10, RI 2"
        in advice.message
    )
    assert "suggested ≥" not in advice.message


def test_single_distinct_ain_does_not_emit_multichannel_table_guidance():
    advice = _resolve_t7(scan_channels=("AIN2", "ain2"))

    assert advice is not None
    assert advice.tag == "INFO"
    assert "only one distinct AIN is scanned" in advice.message
    assert "suggested ≥" not in advice.message


@pytest.mark.parametrize(
    "device_type",
    [
        LabJackDeviceTypeEnum.T4,
        LabJackDeviceTypeEnum.T8,
        LabJackDeviceTypeEnum.U3,
        LabJackDeviceTypeEnum.U6,
        LabJackDeviceTypeEnum.UE9,
        LabJackDeviceTypeEnum.U12,
        LabJackDeviceTypeEnum.DIGIT,
    ],
)
def test_t7_numeric_tables_are_not_reused_for_other_devices(device_type):
    advice = _resolve_stream_settling_advice(
        device_type=device_type,
        scan_channels=("AIN0", "AIN2"),
        input_range_v=1.0,
        resolution_index=1,
        settling_us=0.0,
    )

    assert advice is None
