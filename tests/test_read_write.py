from dataclasses import FrozenInstanceError
from datetime import timezone
import inspect
import math

import pytest

from pylabjack import (
    LabJackDevice,
    LabJackNoConnectionError,
    LabJackReadWriteError,
    ReadWrite,
)
import pylabjack._read_write as read_write_module


class FakeDevice:
    def __init__(self):
        self._handle = object()
        self.device_identity = object()
        self.software_provenance = object()
        self.events = []

    def _check_connection(self):
        self.events.append("connection-checked")


def _install_fake_enames(monkeypatch, returned_read_values=()):
    calls = []
    read_values = iter(returned_read_values)

    def fake_enames(
        handle,
        num_frames,
        names,
        directions,
        num_values,
        values,
    ):
        calls.append(
            (
                handle,
                num_frames,
                names,
                directions,
                num_values,
                values,
            )
        )
        result = list(values)
        for index, direction in enumerate(directions):
            if direction == read_write_module.ljm.constants.READ:
                result[index] = next(read_values)
        return result

    monkeypatch.setattr(read_write_module.ljm, "eNames", fake_enames)
    return calls


def test_read_one_returns_complete_operation_with_value_convenience(monkeypatch):
    calls = _install_fake_enames(monkeypatch, [2.5])
    device = FakeDevice()

    operation = LabJackDevice.read(device, "AIN0")

    assert isinstance(operation, ReadWrite)
    assert operation.method == "read"
    assert operation.requested_input == "AIN0"
    assert operation.value == 2.5
    assert operation.values == (2.5,)
    assert operation.written_values == ()
    assert operation.num_frames == 1
    assert operation.num_reads == 1
    assert operation.num_writes == 0
    assert operation.device_identity is device.device_identity
    assert operation.software_provenance is device.software_provenance
    assert operation.started_at_utc.tzinfo is timezone.utc
    assert operation.finished_at_utc.tzinfo is timezone.utc
    assert operation.finished_at_utc >= operation.started_at_utc
    assert operation.execution_duration_s >= 0.0
    assert "Method: read" in str(operation)
    assert device.events == ["connection-checked"]

    assert calls == [
        (
            device._handle,
            1,
            ["AIN0"],
            [read_write_module.ljm.constants.READ],
            [1],
            [0.0],
        )
    ]


def test_read_sequence_preserves_order_and_duplicate_names(monkeypatch):
    calls = _install_fake_enames(monkeypatch, [1.0, 2.0, 3.0])
    device = FakeDevice()

    operation = LabJackDevice.read(device, ["AIN1", "AIN0", "AIN1"])

    assert operation.ljm_names == ("AIN1", "AIN0", "AIN1")
    assert operation.values == (1.0, 2.0, 3.0)
    assert tuple(result.name for result in operation.results) == (
        "AIN1",
        "AIN0",
        "AIN1",
    )
    with pytest.raises(ValueError, match="exactly one register"):
        _ = operation.value
    assert calls[0][2] == ["AIN1", "AIN0", "AIN1"]


def test_write_supports_single_and_ordered_pair_forms(monkeypatch):
    calls = _install_fake_enames(monkeypatch)
    device = FakeDevice()

    single = LabJackDevice.write(device, "DAC0", 1.25)
    multiple = LabJackDevice.write(
        device,
        [("DAC1", 2), ("DAC0", -0.5), ("DAC1", 3.0)],
    )

    assert single.method == "write"
    assert single.requested_input == ("DAC0", 1.25)
    assert single.values == ()
    assert single.written_values == (1.25,)
    with pytest.raises(ValueError, match="exactly one register"):
        _ = single.value

    assert multiple.ljm_names == ("DAC1", "DAC0", "DAC1")
    assert multiple.written_values == (2.0, -0.5, 3.0)
    assert multiple.num_reads == 0
    assert multiple.num_writes == 3
    assert calls[1][2:] == (
        ["DAC1", "DAC0", "DAC1"],
        [
            read_write_module.ljm.constants.WRITE,
            read_write_module.ljm.constants.WRITE,
            read_write_module.ljm.constants.WRITE,
        ],
        [1, 1, 1],
        [2.0, -0.5, 3.0],
    )


def test_read_write_preserves_mixed_order_and_effective_ljm_frames(monkeypatch):
    calls = _install_fake_enames(monkeypatch, [0.25, 0.5])
    device = FakeDevice()
    requested = [
        {"action": "write", "name": "DAC0", "value": 1.5},
        ("read", "AIN0"),
        {"action": "read", "name": "AIN0"},
        ("write", "DAC0", 2.5),
    ]

    operation = LabJackDevice.read_write(device, requested)
    requested[0]["name"] = "CHANGED_AFTER_CALL"

    assert operation.method == "read_write"
    assert operation.requested_input[0]["name"] == "DAC0"
    requested_copy = operation.requested_input
    requested_copy[0]["name"] = "CHANGED_COPY"
    assert operation.requested_input[0]["name"] == "DAC0"
    assert operation.ljm_names == ("DAC0", "AIN0", "AIN0", "DAC0")
    assert operation.ljm_directions == (
        read_write_module.ljm.constants.WRITE,
        read_write_module.ljm.constants.READ,
        read_write_module.ljm.constants.READ,
        read_write_module.ljm.constants.WRITE,
    )
    assert operation.ljm_num_values == (1, 1, 1, 1)
    assert operation.ljm_values_before == (1.5, 0.0, 0.0, 2.5)
    assert operation.ljm_values_after == (1.5, 0.25, 0.5, 2.5)
    assert operation.values == (0.25, 0.5)
    assert operation.written_values == (1.5, 2.5)
    assert tuple(result.action for result in operation.results) == (
        "write",
        "read",
        "read",
        "write",
    )
    assert calls[0][1] == 4


@pytest.mark.parametrize(
    "bad_names",
    [
        [],
        ["AIN0", 1],
        [" AIN0"],
        ["AIN\n0"],
        ["AIN\N{MICRO SIGN}"],
        {"AIN0": 1},
    ],
)
def test_read_rejects_invalid_or_lossy_name_inputs_before_device_access(
    monkeypatch,
    bad_names,
):
    calls = _install_fake_enames(monkeypatch)
    device = FakeDevice()

    with pytest.raises((TypeError, ValueError)):
        LabJackDevice.read(device, bad_names)

    assert device.events == []
    assert calls == []


@pytest.mark.parametrize(
    ("name_or_entries", "value"),
    [
        ("DAC0", None),
        ("DAC0", True),
        ("DAC0", math.inf),
        ("DAC0", math.nan),
        pytest.param(
            "DAC0",
            10**10_000,
            id="integer-overflows-float",
        ),
        ([], None),
        (["DAC0", 1.0], None),
        ([("DAC0", 1.0, 2.0)], None),
        ([("DAC0", 1.0)], 2.0),
        ({"DAC0": 1.0}, None),
    ],
)
def test_write_rejects_ambiguous_or_nonnumeric_inputs_before_device_access(
    monkeypatch,
    name_or_entries,
    value,
):
    calls = _install_fake_enames(monkeypatch)
    device = FakeDevice()

    with pytest.raises((TypeError, ValueError)):
        LabJackDevice.write(device, name_or_entries, value)

    assert device.events == []
    assert calls == []


@pytest.mark.parametrize(
    "commands",
    [
        [],
        "read AIN0",
        [{}],
        [{"action": "read", "name": "AIN0", "value": 0.0}],
        [{"action": "write", "name": "DAC0"}],
        [{"action": "READ", "name": "AIN0"}],
        [{"action": "read", "name": "AIN0", "typo": 1}],
        [("read", "AIN0", 0.0)],
        [("write", "DAC0")],
        [object()],
    ],
)
def test_read_write_rejects_invalid_commands_before_device_access(
    monkeypatch,
    commands,
):
    calls = _install_fake_enames(monkeypatch)
    device = FakeDevice()

    with pytest.raises((TypeError, ValueError)):
        LabJackDevice.read_write(device, commands)

    assert device.events == []
    assert calls == []


def test_disconnected_device_fails_before_enames(monkeypatch):
    calls = _install_fake_enames(monkeypatch)
    device = FakeDevice()

    def fail_connection_check():
        raise LabJackNoConnectionError("closed")

    device._check_connection = fail_connection_check

    with pytest.raises(LabJackNoConnectionError, match="closed"):
        LabJackDevice.read(device, "AIN0")

    assert calls == []


def test_enames_failure_is_wrapped_without_losing_the_cause(monkeypatch):
    device = FakeDevice()
    original_error = RuntimeError("eNames failed")

    def fail_enames(*args):
        raise original_error

    monkeypatch.setattr(read_write_module.ljm, "eNames", fail_enames)

    with pytest.raises(LabJackReadWriteError, match="Non LabJack") as caught:
        LabJackDevice.read(device, "AIN0")

    assert caught.value.__cause__ is original_error


def test_ljm_enames_failure_uses_library_error_message(monkeypatch):
    class FakeLJMError(Exception):
        pass

    original_error = FakeLJMError("device error")
    monkeypatch.setattr(read_write_module.ljm, "LJMError", FakeLJMError)

    def fail_enames(*args):
        raise original_error

    monkeypatch.setattr(read_write_module.ljm, "eNames", fail_enames)

    with pytest.raises(LabJackReadWriteError, match="library-level") as caught:
        LabJackDevice.read(FakeDevice(), "AIN0")

    assert caught.value.__cause__ is original_error


def test_enames_return_length_must_match_scalar_command_count(monkeypatch):
    device = FakeDevice()
    monkeypatch.setattr(
        read_write_module.ljm,
        "eNames",
        lambda *args: [],
    )

    with pytest.raises(LabJackReadWriteError, match="does not match"):
        LabJackDevice.read(device, "AIN0")


def test_read_write_constructor_requires_normalized_protected_inputs():
    signature = inspect.signature(ReadWrite)

    assert list(signature.parameters) == [
        "device",
        "_method",
        "_requested_input",
        "_commands",
    ]
    assert all(
        signature.parameters[name].kind is inspect.Parameter.KEYWORD_ONLY
        for name in ("_method", "_requested_input", "_commands")
    )


def test_result_entries_are_immutable(monkeypatch):
    _install_fake_enames(monkeypatch, [1.0])
    operation = LabJackDevice.read(FakeDevice(), "AIN0")

    with pytest.raises(FrozenInstanceError):
        operation.results[0].value = 2.0


def test_read_write_has_host_timing_but_no_stream_timestamp_contract(monkeypatch):
    _install_fake_enames(monkeypatch, [1.0])
    operation = LabJackDevice.read(FakeDevice(), "AIN0")

    assert operation.execution_duration_s >= 0.0
    assert not hasattr(operation, "sample_times_s")
    assert not hasattr(operation, "timestamps")
    assert not hasattr(operation, "scan_rate_Hz")
