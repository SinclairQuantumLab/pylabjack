# On-demand numeric register I/O

## Scope

`LabJackDevice.read()`, `write()`, and `read_write()` are synchronous,
command-response operations for named scalar numeric registers. All three
facades normalize into one `ReadWrite` operation and one ordered
[`ljm.eNames()`](https://support.labjack.com/docs/enames-ljm-user-s-guide)
call. No facade maintains a separate execution path.

This is “single-time” rather than “single-channel”: one call can contain many
read and write frames, but pylabjack does not assign per-frame timestamps or
claim simultaneous acquisition, deterministic spacing, or stream-like timing.
The operation records only the UTC host start/end and monotonic elapsed time
observed around the complete `eNames()` call.

The snippets below illustrate input shape. On a connected device they are real
hardware operations, so verify every register, value, model, and electrical
state before substituting them into an authorized run.

## Inputs

The easy read form accepts one register name or an ordered sequence. Order and
duplicates are preserved:

```python
device.read("AIN0")
device.read(["AIN0", "AIN1", "AIN0"])
```

The easy write form accepts one name plus one value or an ordered sequence of
name/value pairs:

```python
device.write("DAC0", 1.0)
device.write([("DAC0", 1.0), ("DAC1", 2.0), ("DAC0", 0.0)])
```

The advanced mixed form accepts an ordered sequence of mappings, compact
tuples/lists, or both:

```python
device.read_write([
    {"action": "write", "name": "DAC0", "value": 1.0},
    {"action": "read", "name": "AIN0"},
    ("write", "DAC0", 0.0),
    ("read", "AIN0"),
])
```

Mapping commands require exactly `action` and `name`, plus `value` only for a
write. Compact commands are exactly `("read", name)` or
`("write", name, value)`. Actions are lowercase and explicit. Register names
must be non-empty ASCII strings without whitespace or control characters.
Write values must be finite, float-representable real numbers; booleans are
rejected.

Every current command has `aNumValues=1`. LJM consecutive numeric-array,
string, byte-array, and address/type functions describe different register
shapes or addressing, not repeated time-spaced acquisition. They remain
unimplemented specialized variants rather than being guessed from input shape.

## Result object

Every facade returns `ReadWrite`, including `read("AIN0")` and write-only calls.
The object retains:

| Property | Meaning |
| --- | --- |
| `method` | The facade used: `read`, `write`, or `read_write`. |
| `requested_input` | A defensive copy of the caller's original input form. |
| `commands` | Immutable normalized commands in hardware order. |
| `results` | Immutable result entries aligned one-for-one with `commands`. |
| `value` | Convenience scalar available only when exactly one register was read. |
| `values` | Read values only, preserving read-command order and duplicates. |
| `written_values` | Requested write values in write-command order. |
| `ljm_names`, `ljm_directions`, `ljm_num_values` | Effective `eNames()` frame arrays. |
| `ljm_values_before`, `ljm_values_after` | The complete value array before and after LJM, including write positions and read placeholders/results. |
| `started_at_utc`, `finished_at_utc`, `execution_duration_s` | Host-observed whole-call timing; not device timestamps. |
| `device_identity` | Immutable device type, connection type, serial number, IP address, and port snapshot. |
| `software_provenance` | The immutable package/Git snapshot shared by the owning device. |

`value` raises `ValueError` for zero or multiple reads so that a write-only or
multi-read operation cannot be silently collapsed. `results` and the effective
LJM arrays remain the complete lossless contract for mixed operations.

## Failure and state boundary

All validation occurs before device access. An LJM or wrapper failure is raised
as `LabJackReadWriteError` with the original exception as its cause. The
operation writes only the registers explicitly represented by write commands;
it does not apply AIN defaults or call the separate legacy
`configure_register()` path.

Device-free tests fake `eNames()` and cover ordering, duplicate names, mixed
frames, return alignment, validation, exception chaining, timing boundaries,
identity, and provenance. Temporary Git tests cover provenance separately. No
native LJM execution or physical LabJack read/write has been performed.
