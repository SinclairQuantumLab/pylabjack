import subprocess
import sys
from pathlib import Path

import numpy as np
import pylabjack

from pylabjack import (
    LabJackConnectionTypeEnum,
    LabJackDevice,
    LabJackDeviceTypeEnum,
    LabJackReadWriteError,
    ReadWrite,
    Stream,
)
from pylabjack._ljm_aux import LabJackaData2chData


def test_public_api_exports_device_and_connection_enums():
    assert LabJackDevice.__name__ == "LabJackDevice"
    assert LabJackDeviceTypeEnum.T7.name == "T7"
    assert LabJackDeviceTypeEnum.U12.value == 1
    assert LabJackDeviceTypeEnum.U3.value == 3
    assert LabJackDeviceTypeEnum.U6.value == 6
    assert LabJackDeviceTypeEnum.UE9.value == 9
    assert LabJackConnectionTypeEnum.USB.name == "USB"
    assert Stream.__name__ == "Stream"
    assert ReadWrite.__name__ == "ReadWrite"
    assert issubclass(LabJackReadWriteError, Exception)
    assert not hasattr(pylabjack, "StreamIn")
    assert not hasattr(LabJackDevice, "stream_in")
    assert not hasattr(pylabjack, "StreamTimingConfig")
    assert not hasattr(pylabjack, "stream_element_timestamps")
    assert not hasattr(pylabjack, "StreamSampleTimeConfig")
    assert not hasattr(pylabjack, "reconstruct_stream_sample_times")
    assert not hasattr(pylabjack, "StreamSettlingAdvice")
    assert not hasattr(pylabjack, "resolve_stream_settling_advice")
    assert not hasattr(pylabjack, "SoftwareProvenance")
    assert not hasattr(pylabjack, "capture_software_provenance")
    assert not hasattr(pylabjack, "LabJackDeviceIdentity")
    assert not hasattr(pylabjack, "ReadWriteCommand")
    assert not hasattr(pylabjack, "ReadWriteResult")


def test_installed_package_imports_in_isolated_mode():
    subprocess.run(
        [sys.executable, "-I", "-c", "import pylabjack"],
        cwd=Path(__file__).parent,
        check=True,
        capture_output=True,
        text=True,
    )


def test_interleaved_data_is_split_by_channel_without_hardware():
    channel_data = LabJackaData2chData(
        [1.0, 10.0, 2.0, 20.0, 3.0, 30.0],
        numAddresses=2,
    )

    np.testing.assert_array_equal(channel_data[0]["idx"], [0, 2, 4])
    np.testing.assert_array_equal(channel_data[0]["V"], [1.0, 2.0, 3.0])
    np.testing.assert_array_equal(channel_data[1]["idx"], [1, 3, 5])
    np.testing.assert_array_equal(channel_data[1]["V"], [10.0, 20.0, 30.0])
    assert all("t" not in record for record in channel_data)
