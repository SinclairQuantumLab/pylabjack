from dataclasses import FrozenInstanceError

import pytest

from pylabjack import (
    LabJackConnectionError,
    LabJackConnectionTypeEnum,
    LabJackDevice,
    LabJackDeviceTypeEnum,
    LabJackDisconnectionError,
    LabJackNoConnectionError,
)
import pylabjack.labjack_device as device_module
import pylabjack._read_write as read_write_module
import pylabjack._stream as stream_module
from pylabjack._software_provenance import SoftwareProvenance


def _install_successful_fake_ljm(monkeypatch):
    events = []

    def open_device(device_type, connection_type, identifier):
        events.append(("open", device_type, connection_type, identifier))
        return 123

    def get_handle_info(handle):
        events.append(("info", handle))
        return (7, 1, 0, 0, 502, 4096)

    def close_device(handle):
        events.append(("close", handle))

    monkeypatch.setattr(device_module.ljm, "openS", open_device)
    monkeypatch.setattr(device_module.ljm, "getHandleInfo", get_handle_info)
    monkeypatch.setattr(device_module.ljm, "numberToIP", lambda value: "0.0.0.0")
    monkeypatch.setattr(device_module.ljm, "close", close_device)
    return events


def _make_device():
    return LabJackDevice(
        device_type=LabJackDeviceTypeEnum.T7,
        connection_type=LabJackConnectionTypeEnum.USB,
        device_identifier="<DEVICE_IDENTIFIER>",
    )


def test_explicit_lifetime_keeps_one_connection_open_until_close(monkeypatch):
    events = _install_successful_fake_ljm(monkeypatch)

    device = _make_device()
    device._check_connection()
    device._check_connection()

    assert [event[0] for event in events].count("open") == 1
    assert [event[0] for event in events].count("close") == 0

    device.close()
    device.close()

    assert [event[0] for event in events].count("close") == 1
    with pytest.raises(LabJackNoConnectionError):
        device._check_connection()


def test_device_captures_one_read_only_software_provenance_snapshot(monkeypatch):
    events = _install_successful_fake_ljm(monkeypatch)
    expected = SoftwareProvenance(
        package_name="pylabjack",
        package_version="0.1.0",
        git_repository_name="pylabjack",
        git_remote_repository="example.com/team/pylabjack",
        git_commit_hash="0123456789abcdef0123456789abcdef01234567",
        is_worktree_dirty=True,
        git_metadata_available=True,
    )
    calls = []

    def fake_provenance_resolver(*, package_name, source_path):
        calls.append((package_name, source_path))
        return expected

    monkeypatch.setattr(
        device_module,
        "get_software_provenance",
        fake_provenance_resolver,
    )

    device = _make_device()

    assert device.software_provenance is expected
    assert calls == [("pylabjack", device_module.__file__)]

    device.close()
    assert [event[0] for event in events].count("close") == 1


def test_device_identity_is_immutable_and_survives_close(monkeypatch):
    _install_successful_fake_ljm(monkeypatch)
    device = _make_device()

    identity = device.device_identity
    assert identity.device_type is LabJackDeviceTypeEnum.T7
    assert identity.connection_type is LabJackConnectionTypeEnum.USB
    assert identity.serial_number == 0
    assert identity.ip_address == "0.0.0.0"
    assert identity.port == 502

    with pytest.raises(FrozenInstanceError):
        identity.port = 0

    device.close()
    assert device.device_identity is identity


def test_on_demand_operation_borrows_connection_without_closing_it(monkeypatch):
    events = _install_successful_fake_ljm(monkeypatch)
    stream_result = object()

    monkeypatch.setattr(
        stream_module,
        "Stream",
        lambda device, *, _plan: stream_result,
    )
    device = _make_device()

    result = device.stream(
        scan_rate_Hz=1_000.0,
        inputs={"channels": ["AIN0"]},
    )

    assert result is stream_result
    assert [event[0] for event in events].count("open") == 1
    assert [event[0] for event in events].count("close") == 0
    device._check_connection()

    device.close()
    assert [event[0] for event in events].count("close") == 1


def test_read_operation_shares_connected_device_metadata_without_closing(
    monkeypatch,
):
    events = _install_successful_fake_ljm(monkeypatch)
    monkeypatch.setattr(
        read_write_module.ljm,
        "eNames",
        lambda handle, count, names, writes, num_values, values: [4.2],
    )
    device = _make_device()

    operation = device.read("AIN0")

    assert operation.value == 4.2
    assert operation.device_identity is device.device_identity
    assert operation.software_provenance is device.software_provenance
    assert [event[0] for event in events].count("close") == 0
    device._check_connection()

    device.close()
    assert [event[0] for event in events].count("close") == 1


def test_context_manager_reuses_constructor_connection_and_closes_once(monkeypatch):
    events = _install_successful_fake_ljm(monkeypatch)
    device = _make_device()

    with device as entered_device:
        assert entered_device is device
        device._check_connection()

    assert [event[0] for event in events].count("open") == 1
    assert [event[0] for event in events].count("close") == 1


def test_entering_an_explicitly_closed_device_does_not_reconnect(monkeypatch):
    events = _install_successful_fake_ljm(monkeypatch)
    device = _make_device()
    device.close()

    with pytest.raises(LabJackNoConnectionError):
        with device:
            pass

    assert [event[0] for event in events].count("open") == 1
    assert [event[0] for event in events].count("close") == 1


def test_context_manager_preserves_body_error_when_close_succeeds(monkeypatch):
    events = _install_successful_fake_ljm(monkeypatch)
    body_error = ValueError("operation failed")

    with pytest.raises(ValueError) as caught:
        with _make_device():
            raise body_error

    assert caught.value is body_error
    assert [event[0] for event in events].count("close") == 1


def test_close_error_is_primary_after_successful_body(monkeypatch):
    _install_successful_fake_ljm(monkeypatch)
    close_should_fail = True

    def close_device(handle):
        if close_should_fail:
            raise RuntimeError("close failed")

    monkeypatch.setattr(device_module.ljm, "close", close_device)
    device = _make_device()

    with pytest.raises(LabJackDisconnectionError, match="Non LabJack"):
        with device:
            pass

    # A failed close remains retryable because the handle is still assigned.
    close_should_fail = False
    device.close()


def test_body_error_stays_primary_when_close_also_fails(monkeypatch):
    _install_successful_fake_ljm(monkeypatch)
    close_should_fail = True

    def close_device(handle):
        if close_should_fail:
            raise RuntimeError("close failed")

    monkeypatch.setattr(device_module.ljm, "close", close_device)
    device = _make_device()
    body_error = ValueError("operation failed")

    with pytest.raises(ValueError) as caught:
        with device:
            raise body_error

    assert caught.value is body_error
    assert any(
        "LabJack close also failed" in note
        for note in caught.value.__notes__
    )

    close_should_fail = False
    device.close()


def test_device_info_failure_rolls_back_the_new_handle(monkeypatch):
    events = []

    monkeypatch.setattr(
        device_module.ljm,
        "openS",
        lambda *args: events.append(("open", args)) or 123,
    )

    def fail_device_info(handle):
        events.append(("info", handle))
        raise RuntimeError("info failed")

    monkeypatch.setattr(device_module.ljm, "getHandleInfo", fail_device_info)
    monkeypatch.setattr(
        device_module.ljm,
        "close",
        lambda handle: events.append(("close", handle)),
    )

    with pytest.raises(LabJackConnectionError, match="loading device info"):
        _make_device()

    assert [event[0] for event in events] == ["open", "info", "close"]
