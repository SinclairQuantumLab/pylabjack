import json
from pathlib import Path
import re


_REPOSITORY_ROOT = Path(__file__).parents[1]
_FACADE_SOURCE = _REPOSITORY_ROOT / "src" / "pylabjack" / "labjack_device.py"
_STREAM_SOURCE = _REPOSITORY_ROOT / "src" / "pylabjack" / "_stream.py"
_HARDWARE_NOTEBOOK = _REPOSITORY_ROOT / "test_labjack_device.ipynb"


def test_module_hardware_example_uses_direct_positional_arguments():
    source = _FACADE_SOURCE.read_text(encoding="utf-8")

    assert "LabJackDeviceTypeEnum[sys.argv[1]]" in source
    assert "LabJackConnectionTypeEnum[sys.argv[2]]" in source
    assert "device_identifier = sys.argv[3]" in source
    assert "<DEVICE_TYPE> <CONNECTION_TYPE> <DEVICE_IDENTIFIER>" in source
    assert "with LabJackDevice(" in source
    assert "del lj_device" not in source
    assert "argparse" not in source


def test_stream_hardware_example_uses_direct_positional_arguments():
    source = _STREAM_SOURCE.read_text(encoding="utf-8")
    main_source = source[source.index('if __name__ == "__main__":'):]

    assert "LabJackDeviceTypeEnum[sys.argv[1]]" in source
    assert "LabJackConnectionTypeEnum[sys.argv[2]]" in source
    assert "device_identifier = sys.argv[3]" in source
    assert "sys.argv[4]" not in source
    assert "scan_rate_Hz = 10_000.0" in source
    assert "duration_s = 1.0" in source
    assert "scans_per_read = 1_000" in source
    assert "resolution_index = 1" in source
    assert "settling_us = 0.0" in source
    assert "ain_range_V = 10.0" in source
    assert 'input_channels = ["AIN0", "AIN1", "AIN4"]' in source
    assert "do_trigger=False" in source
    assert "<DEVICE_TYPE> <CONNECTION_TYPE> <DEVICE_IDENTIFIER>" in source
    assert "# connect to device" in main_source
    assert "device = LabJackDevice(" in main_source
    assert "try:" in main_source
    assert "# perform streaming and return the results" in main_source
    assert "finally:" in main_source
    assert (
        "# disconnect from device when the demo finishes or raises an exception"
        in main_source
    )
    assert "device.close()" in main_source
    assert "with LabJackDevice(" not in main_source
    assert "device._disconnect()" not in main_source
    assert "argparse" not in source


def test_notebook_has_canonical_all_capital_input_template():
    notebook = json.loads(_HARDWARE_NOTEBOOK.read_text(encoding="utf-8"))
    for index, cell in enumerate(notebook["cells"]):
        if cell["cell_type"] == "code":
            compile("".join(cell["source"]), f"notebook-cell-{index}", "exec")
    content = "".join(
        line
        for cell in notebook["cells"]
        for line in cell.get("source", [])
    )

    placeholders = {
        "<DEVICE_TYPE>",
        "<CONNECTION_TYPE>",
        "<DEVICE_IDENTIFIER>",
        "<AIN_CHANNEL_1>",
        "<AIN_CHANNEL_2>",
    }
    assert placeholders <= set(re.findall(r"<[A-Z][A-Z0-9_]*>", content))
    assert "from pylabjack import (" in content
    assert "import numpy as np" in content
    assert "from labjack_device import" not in content
    assert "from _ljm_aux import" not in content
    assert "lj_device.stream(" in content
    assert "lj_device.close()" in content
    assert "del lj_device" not in content


def test_maintained_hardware_examples_contain_no_literal_ipv4_address():
    example_text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (
            _REPOSITORY_ROOT / "README.md",
            _FACADE_SOURCE,
            _STREAM_SOURCE,
            _HARDWARE_NOTEBOOK,
        )
    )

    assert re.search(r"\b(?:\d{1,3}\.){3}\d{1,3}\b", example_text) is None
