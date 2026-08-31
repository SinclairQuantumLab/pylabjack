import inspect

import pytest

from pylabjack import LabJackDevice, LabJackDeviceTypeEnum, Stream
import pylabjack._stream as stream_module
from pylabjack._stream import _normalize_stream_plan


def test_grouped_form_normalizes_inputs_then_outputs_with_distinct_counts():
    waveform = [0.0, 1.0]
    plan = _normalize_stream_plan(
        scan_rate_Hz=1_000.0,
        inputs={
            "resolution_index": 1,
            "settling_us": 0.0,
            "scans_per_read": 500,
            "channels": [
                {"channel": "AIN0", "range_V": 10.0},
                {"channel": "AIN1", "range_V": 10.0},
            ],
        },
        outputs={
            "playback": "periodic",
            "channels": [{"channel": "DAC0", "data": waveform}],
        },
    )

    assert [entry.channel for entry in plan.entries] == ["AIN0", "AIN1", "DAC0"]
    assert [entry.direction for entry in plan.entries] == ["in", "in", "out"]
    assert plan.num_scan_addresses == 3
    assert plan.num_input_addresses == 2
    assert plan.num_output_addresses == 1
    assert plan.output_entries[0].data is waveform


def test_ordered_form_preserves_interleaved_input_output_order():
    plan = _normalize_stream_plan(
        scan_rate_Hz=1_000.0,
        input_config={"resolution_index": 1, "range_V": 10.0},
        output_config={"playback": "aperiodic"},
        channels=[
            {"channel": "AIN0", "mode": "in"},
            {"channel": "DAC0", "mode": "out", "data": [0.0]},
            {"channel": "AIN1", "direction": "in"},
        ],
    )

    assert [entry.channel for entry in plan.entries] == ["AIN0", "DAC0", "AIN1"]
    assert [entry.direction for entry in plan.entries] == ["in", "out", "in"]
    assert plan.output_entries[0].playback == "aperiodic"


def test_grouped_and_ordered_forms_are_mutually_exclusive():
    with pytest.raises(ValueError, match="either inputs/outputs or channels"):
        _normalize_stream_plan(
            scan_rate_Hz=1_000.0,
            inputs={"channels": ["AIN0"]},
            channels=[{"channel": "AIN1", "mode": "in"}],
        )


def test_stream_out_plan_is_rejected_before_device_access():
    plan = _normalize_stream_plan(
        scan_rate_Hz=1_000.0,
        outputs={"channels": [{"channel": "DAC0", "data": [0.0]}]},
    )

    with pytest.raises(NotImplementedError, match="Stream-Out execution"):
        Stream(object(), _plan=plan)


def test_mixed_per_channel_ranges_are_not_silently_mis_timestamped():
    plan = _normalize_stream_plan(
        scan_rate_Hz=1_000.0,
        inputs={
            "channels": [
                {"channel": "AIN0", "range_V": 10.0},
                {"channel": "AIN1", "range_V": 1.0},
            ]
        },
    )

    with pytest.raises(NotImplementedError, match="Per-channel AIN ranges"):
        Stream(object(), _plan=plan)


def test_stream_constructor_requires_one_normalized_plan():
    signature = inspect.signature(Stream)

    assert list(signature.parameters) == ["device", "_plan"]
    assert signature.parameters["_plan"].kind is inspect.Parameter.KEYWORD_ONLY


def test_unified_stream_facade_normalizes_before_constructing_operation(monkeypatch):
    events = []

    class FakeDevice:
        def _check_connection(self):
            events.append("checked")

    def fake_stream(device, *, _plan):
        events.append(_plan)
        return "stream-result"

    monkeypatch.setattr(stream_module, "Stream", fake_stream)

    result = LabJackDevice.stream(
        FakeDevice(),
        scan_rate_Hz=1_000.0,
        inputs={"channels": ["AIN0", "AIN1"]},
    )

    assert result == "stream-result"
    assert events[0] == "checked"
    assert events[1].num_scan_addresses == 2
    assert events[1].num_input_addresses == 2


def test_trigger_timeout_seconds_are_converted_to_ljm_milliseconds(monkeypatch):
    library_configurations = []
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
            library_configurations.append(kwargs)

    monkeypatch.setattr(Stream, "_execute", lambda self: None)
    monkeypatch.setattr(
        stream_module.ljm,
        "nameToAddress",
        lambda name: (0, 0),
    )

    plan = _normalize_stream_plan(
        scan_rate_Hz=1_000.0,
        duration_s=0.001,
        inputs={"channels": ["AIN0"], "scans_per_read": 1},
        do_trigger=True,
        trigger_timeout_s=0.25,
    )
    Stream(FakeDevice(), _plan=plan)

    assert library_configurations[0][
        stream_module.ljm.constants.STREAM_RECEIVE_TIMEOUT_MS
    ] == 250
