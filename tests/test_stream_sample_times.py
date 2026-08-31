import numpy as np
import pytest

from pylabjack import LabJackDeviceTypeEnum
from pylabjack._stream_sample_times import (
    StreamSampleTimeConfig,
    StreamSampleTimeError,
    reconstruct_stream_sample_times,
    resolve_acquisition_schedule,
)
from pylabjack._ljm_aux import LabJackaData2chData
from pylabjack._stream import Stream, _normalize_stream_plan
import pylabjack._stream as stream_module


def test_t7_uses_scan_grid_plus_datasheet_interchannel_delay():
    result = reconstruct_stream_sample_times(
        [1.0, 10.0, 2.0, 20.0],
        StreamSampleTimeConfig(
            device_type=LabJackDeviceTypeEnum.T7,
            actual_scan_rate_hz=25_000.0,
            num_addresses=2,
            resolution_index=0,
            input_range_v=10.0,
        ),
    )

    np.testing.assert_allclose(result.sample_times_s, [0.0, 15e-6, 40e-6, 55e-6])
    np.testing.assert_array_equal(result.scan_indices, [0, 0, 1, 1])
    np.testing.assert_array_equal(result.scan_positions, [0, 1, 0, 1])
    assert result.acquisition_schedule.interchannel_delay_s == pytest.approx(15e-6)
    assert result.acquisition_schedule.resolution_index == 1


def test_t7_high_sample_rate_selects_eight_microsecond_profile():
    schedule = resolve_acquisition_schedule(
        StreamSampleTimeConfig(
            LabJackDeviceTypeEnum.T7,
            50_000.0,
            2,
            resolution_index=1,
            input_range_v=10.0,
        )
    )

    assert schedule.aggregate_sample_rate_hz == 100_000.0
    assert schedule.interchannel_delay_s == pytest.approx(8e-6)


@pytest.mark.parametrize(
    (
        "device_type",
        "scan_rate",
        "num_addresses",
        "resolution",
        "input_range",
        "expected_offsets",
    ),
    [
        (LabJackDeviceTypeEnum.T4, 1_000.0, 4, 0, 10.0, [0.0, 40e-6, 80e-6, 120e-6]),
        (LabJackDeviceTypeEnum.T8, 10_000.0, 4, 1, 10.0, [0.0, 0.0, 0.0, 0.0]),
        (LabJackDeviceTypeEnum.U6, 200.0, 4, 2, 1.0, [0.0, 220e-6, 440e-6, 660e-6]),
        (LabJackDeviceTypeEnum.UE9, 100.0, 2, 14, 10.0, [0.0, 158e-6]),
    ],
)
def test_model_tables_resolve_expected_offsets(
    device_type,
    scan_rate,
    num_addresses,
    resolution,
    input_range,
    expected_offsets,
):
    schedule = resolve_acquisition_schedule(
        StreamSampleTimeConfig(
            device_type=device_type,
            actual_scan_rate_hz=scan_rate,
            num_addresses=num_addresses,
            resolution_index=resolution,
            input_range_v=input_range,
        )
    )

    np.testing.assert_allclose(schedule.channel_offsets_s, expected_offsets)


def test_schedule_requires_existing_device_type_enum():
    with pytest.raises(StreamSampleTimeError, match="LabJackDeviceTypeEnum"):
        resolve_acquisition_schedule(StreamSampleTimeConfig("T7", 1_000.0, 2))


def test_digit_device_is_not_supported_for_stream_sample_times():
    with pytest.raises(StreamSampleTimeError, match="not supported for DIGIT"):
        resolve_acquisition_schedule(
            StreamSampleTimeConfig(LabJackDeviceTypeEnum.DIGIT, 1_000.0, 2)
        )


def test_u3_ud_auto_resolution_uses_highest_resolution_that_meets_sample_rate():
    schedule = resolve_acquisition_schedule(
        StreamSampleTimeConfig(
            device_type=LabJackDeviceTypeEnum.U3,
            actual_scan_rate_hz=2_000.0,
            num_addresses=4,
            resolution_index=None,
        )
    )

    assert schedule.resolution_index == 1
    assert schedule.interchannel_delay_s == pytest.approx(82e-6)


def test_ue9_extra_settling_is_added_to_published_delay():
    schedule = resolve_acquisition_schedule(
        StreamSampleTimeConfig(
            device_type=LabJackDeviceTypeEnum.UE9,
            actual_scan_rate_hz=100.0,
            num_addresses=2,
            resolution_index=14,
            settling_us=10.0,
        )
    )

    assert schedule.interchannel_delay_s == pytest.approx(168e-6)


def test_u12_places_every_flat_sample_on_uniform_sample_grid():
    result = reconstruct_stream_sample_times(
        [1.0, 10.0, 2.0, 20.0],
        StreamSampleTimeConfig(LabJackDeviceTypeEnum.U12, 500.0, 2),
    )

    np.testing.assert_allclose(result.sample_times_s, [0.0, 1e-3, 2e-3, 3e-3])


def test_manual_settling_requires_override_where_manual_has_no_complete_formula():
    with pytest.raises(StreamSampleTimeError, match="manual-settling-to-interchannel-delay"):
        resolve_acquisition_schedule(
            StreamSampleTimeConfig(
                LabJackDeviceTypeEnum.T7,
                1_000.0,
                2,
                settling_us=100.0,
            )
        )

    schedule = resolve_acquisition_schedule(
        StreamSampleTimeConfig(
            LabJackDeviceTypeEnum.T7,
            1_000.0,
            2,
            settling_us=100.0,
            interchannel_delay_s=110e-6,
        )
    )
    assert schedule.interchannel_delay_s == pytest.approx(110e-6)
    assert not schedule.values_are_typical


def test_chunk_start_index_preserves_scan_position_and_dummy_sample_time():
    result = reconstruct_stream_sample_times(
        [-9999.0, 2.0, 20.0],
        StreamSampleTimeConfig(LabJackDeviceTypeEnum.T7, 25_000.0, 2),
        start_element_index=3,
    )

    np.testing.assert_array_equal(result.element_indices, [3, 4, 5])
    np.testing.assert_array_equal(result.scan_positions, [1, 0, 1])
    np.testing.assert_allclose(result.sample_times_s, [55e-6, 80e-6, 95e-6])


def test_explicit_scan_start_times_support_irregular_external_clock():
    result = reconstruct_stream_sample_times(
        [1.0, 10.0, 2.0, 20.0],
        StreamSampleTimeConfig(LabJackDeviceTypeEnum.T7, 1_000.0, 2),
        scan_start_times_s=[0.0, 0.0015],
    )

    np.testing.assert_allclose(result.sample_times_s, [0.0, 15e-6, 1.5e-3, 1.515e-3])


def test_channel_split_uses_actual_scan_spacing_not_flat_index_spacing():
    sample_times = reconstruct_stream_sample_times(
        [1.0, 10.0, 2.0, 20.0, 3.0, 30.0],
        StreamSampleTimeConfig(LabJackDeviceTypeEnum.T7, 25_000.0, 2),
    )
    channel_data = LabJackaData2chData(
        [1.0, 10.0, 2.0, 20.0, 3.0, 30.0],
        numAddresses=2,
        sample_times_s=sample_times.sample_times_s,
    )

    np.testing.assert_allclose(np.diff(channel_data[0]["t"]), [40e-6, 40e-6])
    np.testing.assert_allclose(np.diff(channel_data[1]["t"]), [40e-6, 40e-6])
    np.testing.assert_allclose(channel_data[1]["t"] - channel_data[0]["t"], 15e-6)


def test_invalid_profile_that_overlaps_next_scan_is_rejected():
    with pytest.raises(StreamSampleTimeError, match="does not fit inside"):
        resolve_acquisition_schedule(
            StreamSampleTimeConfig(
                LabJackDeviceTypeEnum.T7,
                actual_scan_rate_hz=10_000.0,
                num_addresses=4,
                resolution_index=1,
                input_range_v=1.0,
            )
        )


def test_stream_uses_actual_rate_returned_by_estreamstart(monkeypatch):
    expected_provenance = object()
    expected_device_identity = object()

    class FakeDevice:
        device_type = LabJackDeviceTypeEnum.T7
        _handle = object()
        software_provenance = expected_provenance
        device_identity = expected_device_identity

        def configure_register(self, **kwargs):
            return None

        def configure_library(self, **kwargs):
            return None

    requested_rates = []
    monkeypatch.setattr(
        stream_module.ljm,
        "namesToAddresses",
        lambda count, names: ([0, 2], [0, 0]),
    )

    def fake_start(handle, scans_per_read, count, addresses, requested_rate):
        requested_rates.append(requested_rate)
        return 900.0

    monkeypatch.setattr(stream_module.ljm, "eStreamStart", fake_start)
    monkeypatch.setattr(
        stream_module.ljm,
        "eStreamRead",
        lambda handle: ([1.0, 10.0, 2.0, 20.0], 0, 0),
    )
    monkeypatch.setattr(stream_module.ljm, "eStreamStop", lambda handle: None)

    plan = _normalize_stream_plan(
        scan_rate_Hz=1_000.0,
        duration_s=0.002,
        inputs={"channels": ["AIN0", "AIN1"], "scans_per_read": 2},
    )
    stream = Stream(FakeDevice(), _plan=plan)

    assert requested_rates == [1_000.0]
    assert stream.actual_scan_rate_Hz == 900.0
    assert stream.actual_sampling_rate_Hz == 1_800.0
    assert stream.actual_scan_address_rate_Hz == 1_800.0
    assert stream.scan_list == ["AIN0", "AIN1"]
    assert stream.input_channels == ["AIN0", "AIN1"]
    assert stream.output_channels == []
    assert stream.num_scan_addresses == 2
    assert stream.num_input_addresses == 2
    assert stream.num_output_addresses == 0
    assert stream.software_provenance is expected_provenance
    assert stream.device_identity is expected_device_identity
    assert not hasattr(stream, "timing")
    assert not hasattr(stream, "element_timestamps")
    assert not hasattr(stream, "interleaved_timestamps_s")
    np.testing.assert_allclose(
        stream.interleaved_sample_times_s,
        [0.0, 15e-6, 1.0 / 900.0, 1.0 / 900.0 + 15e-6],
    )


def test_stream_emits_settling_advice_before_register_writes(
    monkeypatch, capsys
):
    events = []
    expected_provenance = object()
    expected_device_identity = object()

    class FakeDevice:
        device_type = LabJackDeviceTypeEnum.T7
        _handle = object()
        software_provenance = expected_provenance
        device_identity = expected_device_identity

        def configure_register(self, **kwargs):
            events.append(("configure_register", kwargs))

    monkeypatch.setattr(Stream, "_execute", lambda self: events.append(("stream",)))

    plan = _normalize_stream_plan(
        scan_rate_Hz=1_000.0,
        duration_s=0.002,
        inputs={
            "channels": ["AIN0", "AIN2"],
            "scans_per_read": 2,
            "resolution_index": 1,
            "ain_range_V": 1.0,
        },
    )
    stream = Stream(FakeDevice(), _plan=plan)

    output = capsys.readouterr().out
    assert output.startswith(
        "INFO: STREAM_SETTLING_US value (currently Auto (200 µs))"
    )
    assert output.index("INFO: ") < output.index(">>> Configuring LabJack")
    assert events[0][0] == "configure_register"
    assert events[0][1]["STREAM_SETTLING_US"] == 0.0
    assert events[1] == ("stream",)
    assert not hasattr(stream, "settling_advice")
