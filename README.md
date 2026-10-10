# pylabjack

`pylabjack` provides a Pythonic interface to LabJack's `labjack.ljm` API.
Use one `LabJackDevice` connection for on-demand register reads and writes or
stream acquisition. Each operation returns an object containing its settings,
results, device identity, and software provenance.

## Installation

Python 3.11 is required. Version 0.1.0 is currently available from this source
repository and has not been released to a package index. LabJack's native LJM
runtime is a separate system prerequisite for device communication; installing
`labjack-ljm` alone does not install it.

From a source checkout, create the environment and install the library with
[uv](https://docs.astral.sh/uv/):

```powershell
uv sync
```

This installs the library, pytest, Jupyter kernel support, and plotting
dependencies together. Use the resulting project environment for Python
scripts or as your notebook kernel. Import the public API from `pylabjack`.

## Connect to a device

Replace all-capital placeholders with your selected device and connection
values before running the examples. They communicate with real hardware.

Each LabJack device is represented by a `LabJackDevice` object. Its
constructor accepts the values needed to identify and connect to the device,
and opens one connection. The connection remains available across any number
of on-demand operations until `close()` is called. `close()` is idempotent,
so calling it again after a successful close is harmless.

Use `print(lj_device)` to display the device details explicitly.

```python
from pylabjack import (
    LabJackConnectionTypeEnum,
    LabJackDevice,
    LabJackDeviceTypeEnum,
)

# connect to LabJack
lj_device = LabJackDevice(
    device_type=LabJackDeviceTypeEnum["<DEVICE_TYPE>"],
    connection_type=LabJackConnectionTypeEnum["<CONNECTION_TYPE>"],
    device_identifier="<DEVICE_IDENTIFIER>",
)

try:
    # Run operations whenever they are needed while this connection stays open.
    first_stream = lj_device.stream(...)
    second_stream = lj_device.stream(...)
finally:
    # Disconnect when the application finishes or an operation raises.
    lj_device.close()
```

For a bounded connection lifetime, use the same object as a context manager.
Entering the context reuses the connection opened by construction, and exit
closes it even when the body raises:

```python
with LabJackDevice(
    device_type=LabJackDeviceTypeEnum["<DEVICE_TYPE>"],
    connection_type=LabJackConnectionTypeEnum["<CONNECTION_TYPE>"],
    device_identifier="<DEVICE_IDENTIFIER>",
) as lj_device:
    stream = lj_device.stream(...)
```

## On-demand register reads and writes

Run these examples while `lj_device` is connected, inside the `try` or `with`
scope shown above.

`read()`, `write()`, and `read_write()` all return a complete `ReadWrite`
operation object. They execute one ordered command-response transaction through
LJM `eNames()`; they do not perform a timed stream or imply that multiple reads
are simultaneous.

```python
# One read: use .value as a convenience while retaining the full operation.
single = lj_device.read("<READ_REGISTER>")
print(single.value)

# Multiple reads preserve order and duplicate names.
multiple = lj_device.read([
    "<READ_REGISTER_1>",
    "<READ_REGISTER_2>",
])
print(multiple.values)

# Write one register or an ordered sequence of (name, value) pairs.
one_write = lj_device.write("<WRITE_REGISTER>", 0.0)
many_writes = lj_device.write([
    ("<WRITE_REGISTER_1>", 0.0),
    ("<WRITE_REGISTER_2>", 0.0),
])

# Advanced mixed ordering: mapping and compact tuple commands may be combined.
mixed = lj_device.read_write([
    {"action": "write", "name": "<WRITE_REGISTER>", "value": 0.0},
    ("read", "<READ_REGISTER>"),
])
```

The returned object retains the original request, immutable normalized commands
and aligned results, effective LJM frame arrays, UTC host start/end and elapsed
time, immutable device identity, and software provenance. `.values` contains
read results only; `.written_values` contains requested write values. Current
support is limited to one finite numeric value per named register. Consecutive
numeric arrays, strings, byte arrays, and address/type calls remain separate,
unimplemented variants. See [on-demand numeric register I/O](docs/read-write.md)
for the complete input and result contract.

## Streaming

Start streaming through `LabJackDevice.stream()`, and use the returned
`Stream` object for its settings and input results. Finishing one stream does
not disconnect the device, so the same `LabJackDevice` can be used for later
operations until `close()` is called. Input and future Stream-Out are handled
as parts of one device stream session rather than as independently started
streams.

`stream()` is synchronous: it blocks while acquiring data and returns the
operation with its results ready, or raises an execution error. This behavior
is the same in scripts and Jupyter notebooks, including when an event loop is
already running. Asynchronous stream execution is not available.

```python
# Grouped input configuration
stream = lj_device.stream(
    scan_rate_Hz=25e3,
    duration_s=1,
    inputs={
        "resolution_index": 1,
        "settling_us": 0,
        "channels": [
            {"channel": "AIN0", "range_V": 10.0},
            {"channel": "AIN1", "range_V": 10.0},
        ],
    },
    do_trigger=True,
)

# access to the result and stream settings
import numpy as np

print(stream)
print(stream.actual_scan_rate_Hz)
print(stream.interleaved_sample_times_s)
total_nans = np.sum([np.isnan(value['V']).sum() for value in stream.records.values()])
print(f"Recounting skipped total samples = {total_nans}")
```

An explicitly ordered `channels=[...]` form is also accepted, using
`mode="in"` or `mode="out"` on each entry plus optional `input_config` and
`output_config`. Do not combine that form with grouped `inputs`/`outputs` in
one call. Periodic and aperiodic Stream-Out execution is not implemented yet,
so output entries currently raise `NotImplementedError` before device
configuration. `LabJackDevice.stream()` is the only public stream method and
always returns the unified `Stream` operation object.

### Sample times and settling advice

Stream results include reconstructed sample times based on the actual scan rate
and the device's within-scan acquisition schedule. The reconstruction is an
internal part of `Stream`, not a separate public API. See
[Stream sample-time reconstruction](docs/stream-sample-times.md) for the
formula, assumptions, supported models, limitations, and manual references.

Before a T7 stream starts, `Stream` also prints a compact, conditional
settling advisory derived from the configured range, resolution, settling, and
scan list. It does not accept or infer source resistance. See
[T7 stream settling advice](docs/stream-settling-advice.md) for the exact
message rules, table coverage, and electrical limitations.

## Jupyter hardware test notebook

The notebook includes single-register reads and writes, consecutive reads,
and multi-register reads of `AIN0`, `AIN1`, and `AIN2` plotted with channel
legends, followed by stream acquisition and plotting. Consecutive read plots
use the reading index rather than a timed acquisition schedule.

The connection cell registers `lj_device.close` with `atexit` as a fallback
for normal Python process exit. Call `lj_device.close()` when finished;
closing a notebook tab or interrupting a cell does not invoke that callback.

The examples in this README and the notebook created from
[`test_labjack_device.ipynb.template`](test_labjack_device.ipynb.template) access real hardware.
Replace all-capital placeholders such as `<DEVICE_IDENTIFIER>` only with an
explicitly selected device or channel; do not run them as smoke tests.

Copy the template to `test_labjack_device.ipynb` and open that working copy
with the project's notebook environment. The working copy is ignored by Git,
so local connection details and saved outputs stay outside version control.
If it already exists, use it and skip the copy command to preserve its inputs
and outputs.

```powershell
Copy-Item test_labjack_device.ipynb.template test_labjack_device.ipynb
```

## Software provenance

`LabJackDevice` captures one immutable pylabjack software-provenance snapshot
before connecting, and every operation object created by that device shares the
same snapshot. Access it through `device.software_provenance` or, for example,
`stream.software_provenance`.

The snapshot contains the installed package name/version and, when the package
source is inside a Git worktree, the repository name, credential-free `origin`
repository identifier, full `HEAD` commit hash, and worktree-dirty state.
`is_worktree_dirty` includes staged, unstaged, deleted, and untracked files but
excludes ignored files. Git metadata unavailable from an installed wheel or a
system without Git is represented by `git_metadata_available=False` and `None`
Git fields; it never prevents a device operation. A dirty flag qualifies the
commit but cannot reproduce the exact uncommitted changes by itself.

## Stream support and limitations

Stream acquisition currently supports internally clocked AIN input with one
common range and GND-referenced channels. Stream-Out, combined input/output,
non-AIN inputs, differential inputs, mixed ranges, and external clocks are
not implemented. The current path is designed around T4/T7/T8; physical
hardware and firmware compatibility have not yet been validated.

Triggered-stream support, cleanup after stream failures, exact final-block
length, and distinct results for
repeated channel names remain incomplete. See the
[stream capability ledger](docs/stream-capabilities.md) for the complete
support boundaries and validation status.

## Developer's note

This work put a massive effort on the code style.

Let's comply with [PEP 8 Style Guide for Python Code](https://peps.python.org/pep-0008/) as much as possible. Particular focuses on this aspect are highlighted in [Code Style](#code-style) section.

### Development setup

The project uses a `src/pylabjack` package layout, a committed uv lockfile,
and the `uv_build` backend. Set up the development dependencies with:

```powershell
uv sync
```

Declare dependencies and dependency groups in `pyproject.toml`. When those
declarations change, regenerate `uv.lock` with `uv lock`, then update the
environment with `uv sync` and commit both files together. Keep the development
interpreter in `.python-version` within the declared `requires-python` range.

Choose focused checks appropriate to the change. For example:

```powershell
uv run pytest tests/test_read_write.py -k test_read_one
```

Default pytest settings exclude `native_ljm` and `hardware` tests. The full
suite is available when explicitly requested or approved. Contributor
validation guidance is in [`.agents/workflows.md`](.agents/workflows.md).
To build the source distribution and wheel when needed:

```powershell
uv build
```

### Implementation guide

`src/pylabjack/labjack_device.py`, `src/pylabjack/_read_write.py`, and
`src/pylabjack/_stream.py` illustrate the implementation pattern.

- `LabJackDevice` owns the LJM handle and exposes public operation methods.
- Each substantial operation lives in a protected module and is implemented
  by an operation/result class. The public device method returns that object.
- Operation classes retain their settings and results, expose user-facing
  properties, and provide a useful `__str__()` summary.
- Add focused hardware-free tests under `tests/` when they provide useful
  evidence for a behavior change. Simple changes may omit tests.
- Hardware demos remain explicit, opt-in operations and are not generic tests.

### Module hardware demos

The two in-module hardware examples use direct positional arguments without an
argument parser:

```powershell
uv run python -m pylabjack.labjack_device <DEVICE_TYPE> <CONNECTION_TYPE> <DEVICE_IDENTIFIER>
uv run python -m pylabjack._stream <DEVICE_TYPE> <CONNECTION_TYPE> <DEVICE_IDENTIFIER>
```

Missing or malformed device-selection values deliberately retain their Python,
enum, or LJM errors. The stream module fixes its untriggered demonstration at a
10 kHz scan rate for 1 second over `AIN0`, `AIN1`, and `AIN4`, using resolution
index 1, auto settling, ±10 V range, and 1000 scans/read. Supplying valid device
values makes these commands hardware-active; verify the illustrative settings
against the exact model and electrical setup before running it.

### Code style

Follow [PEP 8](https://peps.python.org/pep-0008/) and the conventions below.

- Thorough and explicit type checking
- Highly compliant with [naming conventions](https://peps.python.org/pep-0008/#naming-conventions)
  - It is not only about naming but explicit designation of the variabls' rules and access scope! Some examples :
    - Typical variable: lowercase
    - Constant: UPPERCASE
    - Class: CapWords in general. Exceptional cases exist (e.g., naming for `Exception`s).
    - Access modifiers for variables and functions/methods, and script files: python interpreter doesn't care but still nice to be considerate.
      - public: (name)
      - protected: _(name) (single underscores at the beginning)
      - private: __(name) (double underscores at the beginning)
      - Particular focuses here:
        - Only the properties and methods that shall be accessed or called by user should be named as public.
        - Internal variables and methods should be named as `protected`.
        - `Enum` is a class and thus has name with CapWords form.
    - Avoid using any forms that are reserved for other things in the style guide.
- Clear distinction between and implementation of properties and internal variables of classes.
  - (read-only) properties is set by defining their getters using `@property` decorator. Actual data should be stored in the corresponding internal variables named with `_my_obj` form.
  Setter (i.e., Write access to the public) is set by adding `@[variable_name].setter` decorator.
  
  ```python
  @property
  def my_obj(self): return self._my_obj
  @my_obj.setter
  def my_obj(self, value): self._my_obj = value
  ```

- Wrap finite, pre-defined argument values of functions/methods in `Enum` whenever possible. Shared enums are defined in `src/pylabjack/_ljm_aux.py`; package modules import the names they use explicitly, and users import supported public names from `pylabjack`.

    ```python
    # Example: Enum that lists the supported connection methods
    class LabJackConnectionTypeEnum(Enum):
        USB = ljm.constants.ctUSB
        ETHERNET = ljm.constants.ctETHERNET
        WIFI = ljm.constants.ctWIFI
    ```

    See [this section](#connect-to-a-device) for an example of how it is used.
