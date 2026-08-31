# Pythonic Labjack library

The official python wrapper in `labjack-ljm` package is a literal translation of its native C API rather than *paraphrasing* it in pythonic way. It makes the wrapper horrible to comprehend and use. 

The goal of this project is to wrap the official wrapper once more and use LabJacks with pythonic codes.

Let's comply with [PEP 8 Style Guide for Python Code](https://peps.python.org/pep-0008/) as much as possible. Particular focuses on this aspect are highlighted in [Code Style](#code-style) section.


## Development setup

This repository is a [uv](https://docs.astral.sh/uv/) library project supporting Python 3.11. LabJack's native LJM runtime is installed separately from `labjack-ljm` and must be available for LJM function calls and device communication.

```powershell
# Create/update the environment, including the hardware-free test dependency.
uv sync

# Run the default tests (native-LJM and hardware tests are excluded).
uv run pytest

# Optional dependencies for the notebook.
uv sync --group notebook

# Build the source distribution and wheel.
uv build
```

Import the public API from the installed package:

```python
from pylabjack import (
    LabJackConnectionTypeEnum,
    LabJackDevice,
    LabJackDeviceTypeEnum,
    ReadWrite,
    Stream,
)
```

The examples later in this README and the checked-in
[`test_labjack_device.ipynb`](test_labjack_device.ipynb) access real hardware.
Replace all-capital placeholders such as `<DEVICE_IDENTIFIER>` only with an
explicitly selected device or channel; do not run them as smoke tests.

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


## On-demand register reads and writes

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


## Stream capability status

The current executor is intentionally narrower than LabJack's complete stream
feature set. See the maintained
[stream capability and implementation status](docs/stream-capabilities.md) for
the LJM-function, device-family, channel, clock/trigger, Stream-Out, result, and
validation matrix. In particular, configuration syntax or vendor support does
not by itself mean that `pylabjack` executes a capability.


## Stream sample times

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


## Structure, usage & implementation guide

`src/pylabjack/labjack_device.py` and `src/pylabjack/_stream.py` illustrate the current implementation pattern.

- Each LabJack device is represented by a `LabJackDevice` object. Its
  constructor accepts the values needed to identify and connect to the device,
  and opens one connection. The connection remains available across any number
  of on-demand operations until `close()` is called. `close()` is idempotent,
  so calling it again after a successful close is harmless.

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

- Start streaming through `LabJackDevice.stream()`, and use the returned
  `Stream` object for its settings and input results. Finishing one stream does
  not disconnect the device, so the same `LabJackDevice` can be used for later
  operations until `close()` is called. Input and future Stream-Out are handled
  as parts of one device stream session rather than as independently started
  streams.

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

- Each function class should implement a nice text representation of the measurement results via `__str__()` method.
- Each implemented feature should have hardware-free tests under `tests/`. Hardware demos must remain explicit, opt-in operations and must not be used as generic tests.


## Code style

This work put a massive effort on the code style.

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

    See [this section](#structure-usage--implementation-guide) for an example of how it is used.
