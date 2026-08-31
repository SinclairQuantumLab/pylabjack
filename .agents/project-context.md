# Project context and architecture

Last source review: 2026-08-30

## Purpose and maturity

`pylabjack` is intended to make LabJack's low-level `labjack.ljm` wrapper more Pythonic. It is now an experimental uv library project with `pyproject.toml`, a committed `uv.lock`, an `uv_build` package, and basic device-free tests. Version 0.1.0 is buildable but not released; CI and a release process do not yet exist.

The design described by the README is:

1. Represent each physical device with a `LabJackDevice` object.
2. Put each substantial LabJack operation in its own protected module, implemented by an operation/result class.
3. Expose the operation through a `LabJackDevice` method that returns that class instance.
4. Keep settings and results on the returned object and provide a useful text representation.

Implemented operations are a unified stream session, currently with an all-AIN
input-only execution backend, and ordered on-demand scalar numeric register I/O
through one `ReadWrite`/`ljm.eNames()` backend.

## Near-term implementation priority

Command-response, on-demand device-register reads and writes are now
implemented. One ordered `read_write()` operation backed by `ljm.eNames()` is
the canonical compiler/executor and advanced interface.
User-facing `read()` and `write()` are restricted facades over that same path,
not separate implementations: `read()` accepts one register/channel name or an
ordered sequence of names, while `write()` accepts one name/value pair or an
ordered sequence of pairs. Canonical sequences preserve hardware order and
duplicates; mappings, if accepted, are convenience syntax only. Consecutive
numeric arrays, strings, byte arrays, and address/type-based access remain
specialized variants to add through the same coherent model; they are not
implemented support and are never inferred from scalar input shape.

All three facade calls return the complete command-response operation object;
even an easy one-register `read()` does not collapse the public return value to
a bare float. Like `Stream`, the object retains original inputs, normalized
ordered entries, effective LJM frames, aligned results, host-observed start/end
and duration values, a snapshot of relevant device identity, and software
provenance. `.value` is available only for exactly one read, `.values` preserves
read order and duplicates, `.written_values` preserves requested writes, and
immutable `commands`/`results` plus effective LJM arrays retain the complete
mixed-operation contract.

Software provenance is captured through one immutable `SoftwareProvenance`
value cached per process/source path, stored by `LabJackDevice`, and shared by
every operation object it creates. It contains the installed package name and
version, local repository name, credential-free normalized `origin` repository
identifier when present, full `git_commit_hash`, separate
`is_worktree_dirty`, and explicit Git-availability state. Preserve the full
last-commit hash even when the checkout is dirty; the boolean adds necessary
qualification rather than replacing that hash. In this project,
`is_worktree_dirty` covers staged index changes, unstaged tracked
changes/deletions, and untracked files, while ignored files do not count. The
current checkout demonstrates why both fields matter: an operation may run at a
known `HEAD` while uncommitted source differs from that commit. More granular
flags such as `has_untracked_files` can be added if useful, but do not weaken the
summary boolean's defined semantics. Use Git plumbing (or a library that
implements the full rules) rather than assuming `.git/HEAD` contains a commit:
symbolic and packed refs, linked worktrees, and submodules can make `.git`
indirect. The value is resolved automatically at runtime and is never a source
constant that a developer updates by hand. Capture it before operation timing
starts and cache an immutable process/device snapshot so Git inspection does
not contaminate hardware timing. A source tree digest can be added later if
exact dirty-checkout reproducibility is required. Absence of Git metadata in a
built wheel is represented explicitly rather than causing a hardware operation
to fail. Branch/head-ref is intentionally absent: it is a mutable label and is
unnecessary for commit identity or retrieval.

Precise timing is a Stream-specific design concern. Command-response operations
preserve requested order but do not reconstruct per-entry sample times or imply
simultaneous acquisition, deterministic spacing, or device-side timestamps.
Host-observed timing may be retained when useful, but it must not be presented
with stream-like precision.

## Repository map

| Path | Current responsibility | Important side effects or caveats |
| --- | --- | --- |
| `src/pylabjack/labjack_device.py` | `LabJackDevice` facade and sole LJM-handle owner; immutable identity/provenance snapshots; public idempotent `close()`/context lifetime; connection information; LJM library/register configuration; public read/write/stream entry points | Construction captures provenance, opens hardware, captures actual device identity, and prints connection data. The connection persists across operations until explicit close or context exit. Its `__main__` demo takes device-type, connection-type, and identifier positionally, then writes registers inside a bounded context. |
| `src/pylabjack/_read_write.py` | Unified `ReadWrite` command-response operation; input normalization; scalar `eNames()` frame compilation/execution; aligned results and host timing | `read()`, `write()`, and `read_write()` all enter this backend. It changes only explicitly requested write registers, preserves frame order/duplicates, and makes no simultaneous/per-frame timestamp claim. Numeric arrays, strings, byte arrays, and address/type variants are deferred. |
| `src/pylabjack/_stream.py` | Unified `Stream` operation/result object; grouped/ordered plan normalization; private T7 settling advice; stream/trigger configuration; reading; result assembly; concise module-level support boundary | Construction immediately performs supported input-only plans. It owns the matching stream-start/stop lifecycle but only borrows the device handle and never disconnects it. Its `__main__` demo holds an explicitly constructed device through a `try` block and closes it in `finally`, leaving room for a future awaited asynchronous call; it takes only device type, connection type, and identifier positionally and fixes AIN0/AIN1/AIN4, 10 kHz, 1 second, 1000 scans/read, RI 1, auto settling, ±10 V, and no trigger. Output entries are represented but rejected before device configuration because Stream-Out execution is deferred. Keep its module docstring synchronized with `docs/stream-capabilities.md`. |
| `src/pylabjack/_ljm_aux.py` | Device/connection/trigger enums, custom exceptions, interleaved-data conversion, and TypedDict definitions | Splits a precomputed sample-time array alongside flat data; its legacy scan-rate-only path assigns a common nominal time to each scan. |
| `src/pylabjack/_stream_sample_times.py` | Private resolution of device/configuration acquisition schedules and flat element sample-time reconstruction | Uses the existing `LabJackDeviceTypeEnum` and covers documented T4/T7/T8/U3/U6/UE9/U12 schedules; DIGIT is unsupported. U-family profiles are device-independent calculations and do not imply an LJM connection backend. |
| `src/pylabjack/_software_provenance.py` | Standard-library-only immutable package/Git provenance capture and process cache | Uses bounded, noninteractive Git commands; stores no local root path or credential-bearing raw remote URL. Git/distribution absence is metadata, not an operation failure. The module has no LabJack dependency and is intentionally easy to extract later. |
| `src/pylabjack/__init__.py` | Explicit public package API | Exports the device facade, `ReadWrite`, unified `Stream`, supported enums, and custom errors. The removed `StreamIn` name is intentionally absent. |
| `pyproject.toml` / `uv.lock` / `.python-version` | Python 3.11 support, runtime and dependency groups, pytest markers, build backend, source-document inclusion, and exact resolution | `uv.lock` is committed; update it whenever dependency metadata changes. Detailed `docs/**` are included in the sdist, not installed as wheel data. |
| `tests/test_package.py` | Device-free package/API and interleaved-data smoke tests | Imports the wrapper but never opens/searches for a device or calls native LJM functions. |
| `tests/test_software_provenance.py` | Immutable/cache/absence/remote-sanitization tests plus real temporary Git worktree states | Standard-library and Git only; never invokes native LJM or accesses hardware. Git-dependent cases skip if the executable is absent. |
| `tests/test_read_write.py` | Scalar read/write/mixed normalization, one-call LJM frames, ordering/duplicates, results, validation, errors, host timing, identity, and provenance | Fakes `ljm.eNames()` and never invokes native LJM or accesses hardware. |
| `tests/test_device_lifecycle.py` | Fake-LJM device-handle ownership, explicit/context cleanup, and exceptional-path tests | Verifies the persistent and bounded lifetime contracts without loading the native runtime or accessing hardware. |
| `tests/test_hardware_examples.py` | Static hardware-example argument/template and no-literal-IP checks | Parses source/notebook text only; never executes a hardware path. |
| `tests/test_stream_sample_times.py` | Model-table, chunk-boundary, skipped-position, external-clock, channel-splitting, and fake-LJM actual-rate tests | Imports the private reconstructor for device-free verification; it does not load the native LJM runtime or access hardware. |
| `tests/test_stream_settling_advice.py` | T7 table-branch, severity, compact-output, device-boundary, and tagged-format tests | Verifies exact published values without supplying or inferring source resistance. |
| `tests/test_stream_plan.py` | Unified grouped/ordered plan, scan-order/count, deferred-output, mixed-range, and legacy-delegation tests | Device-free; verifies rejection occurs before device access. |
| `docs/stream-sample-times.md` | Sample-time reconstruction contract, complete model/profile matrix, limitations, and table-level source links | Documents an internal `Stream` mechanism and distinguishes scheduled acquisition times from analog settling accuracy and host-return timing. |
| `docs/stream-settling-advice.md` | T7 settling-advisory contract, exact table coverage, message semantics, and source links | Public explanation of an internal preflight mechanism; not a circuit-validation promise. |
| `docs/stream-capabilities.md` | Canonical stream capability/status ledger across LJM primitives, device families, channels, modes, timing, results, and validation | Separates vendor support, plan-only syntax, calculation-only timing, implemented execution, and hardware validation. It must remain synchronized with `_stream.py`, tests, safety guidance, and known issues. |
| `docs/read-write.md` | Public on-demand scalar numeric read/write input, result, timing, failure, and support contract | Documents one ordered `eNames()` backend and clearly defers array/string/byte/address variants and hardware validation. |
| `test_labjack_device.ipynb` | User-owned manual hardware test template | Not an automated test. It uses canonical package imports, unified `stream()`, and all-capital placeholders for device/channel inputs; do not execute it automatically. |
| `ljm_startup_configs.json` | Vendor-derived LJM 1.2100 startup configuration reference | The Python code does not load it, and uv distributions intentionally exclude it. Leading `//` comments mean it is not strict JSON; preserve the vendor format until its role is deliberately changed. |
| `README.md` | Project intent, uv setup, style, and public usage examples | Hardware examples remain opt-in and are not smoke tests. |
| `.gitignore` | Generated/editor/environment exclusions | It is a merged generic template; broad and conflicting rules are tracked as maintenance debt. |

## Component and data flow

```text
caller
  -> LabJackDevice
       -> _software_provenance: capture/cache package and Git identity once
       -> labjack.ljm: open/configure/close
       -> ReadWrite
            -> normalize easy or advanced request into ordered scalar commands
            -> labjack.ljm.eNames: one mixed read/write transaction
            -> aligned immutable results + host-observed whole-call timing
       -> Stream
            -> share the device's immutable software-provenance snapshot
            -> normalize grouped or ordered configuration into one StreamPlan
            -> private settling resolver: conditional preflight message
            -> labjack.ljm: configure/start/read/stop
            -> eStreamStart return: actual scan rate
            -> queue worker: accumulate flat interleaved samples
            -> _stream_sample_times: scan grid + within-scan acquisition schedule
            -> one element-aligned sample-time array
            -> LabJackaData2chData: split values and precomputed times by channel
            -> records[channel] = {"V": ndarray, "t": ndarray}
```

`LabJackDevice` alone owns the native LJM handle. `Stream` borrows that protected
handle and uses the device's configuration methods; it may stop the stream it
started but may not close the device connection. This is tight coupling rather
than dependency injection, so hardware-free behavior tests use a fake/mocked
LJM boundary.

## Current lifecycle

1. `LabJackDevice.__init__()` stores the requested identifiers, obtains the process-cached pylabjack software-provenance snapshot before hardware timing, and calls `_connect()` once. `_connect()` keeps the new handle local until `getHandleInfo()` and IP conversion succeed; a post-open initialization failure closes that unpublished handle before propagating a connection error.
2. A successfully constructed device stays connected across repeated configuration and operation calls. `__enter__()` validates and returns that same connection rather than opening another one.
3. `read()`, `write()`, and `read_write()` normalize their respective inputs and construct one synchronous `ReadWrite`, which executes exactly one `eNames()` call and never closes the device.
4. `configure_library()` writes process-global LJM configuration, and `configure_register()` writes device registers through its older configuration path.
5. `stream()` normalizes either public configuration form and constructs `Stream`, whose protected-plan constructor validates current support, configures, and runs the entire measurement before returning in a normal synchronous script. It is the only public stream facade and never closes the device.
6. Long-lived callers end the connection explicitly with idempotent `close()`; bounded callers use `with LabJackDevice(...)`. Context exit preserves a body exception if close also fails and attaches the close failure as an exception note. A failed `ljm.close()` leaves the handle assigned so the caller can retry because closure was not confirmed.
7. `__del__()` is only a best-effort fallback and is not part of the deterministic cleanup contract.

## Command-response read/write contract

- `read_write()` is the complete ordered mixed interface. It accepts mapping
  commands or exact compact `("read", name)` / `("write", name, value)`
  sequences; both forms normalize immediately into immutable commands.
- `read()` accepts one name or an ordered sequence of names. `write()` accepts
  one name plus one value or an ordered sequence of `(name, value)` pairs.
  Every facade returns `ReadWrite`, never a bare scalar, list, or `None`.
- One operation makes exactly one `ljm.eNames()` call. Current frames are named
  scalar numeric access with `aNumValues=1`; order and duplicate names remain
  intact across names, directions, value arrays, commands, and results.
- `.value` requires exactly one read; `.values` contains ordered read results;
  `.written_values` contains ordered requested writes. Effective LJM arrays are
  exposed separately so mixed write/read positions are never lost.
- Host UTC start/end and monotonic whole-call duration are observations of the
  complete call only. They are not device timestamps and provide no per-entry
  timing, simultaneity, or deterministic-spacing claim.
- Normalization rejects empty/non-ASCII/whitespace/control-character names,
  ambiguous shapes, non-finite/non-real/non-float-representable write values,
  booleans, unknown keys, and invalid actions before checking the connection or
  calling LJM.
- Consecutive numeric arrays, strings, byte arrays, and address/type access are
  distinct future register-shape variants, not repeated sampling and not
  silently inferred by the scalar interface.

## Stream calculation and result contract

- `stream()` accepts `scan_rate_Hz` directly. The former aggregate-input-rate facade and direct constructor were removed; callers specify scan rate rather than relying on implicit division by the number of read addresses.
- One scan is one reading for every configured channel.
- The requested sample/scan counts are rounded upward so the final logical scan includes every channel.
- `ljm.eStreamRead()` returns interleaved samples. The code counts `-9999.0` sentinel values as skipped samples and replaces them with `numpy.nan`.
- The current execution/result contract is limited to all-AIN input. The normalized plan already distinguishes `num_scan_addresses`, `num_input_addresses`, and `num_output_addresses`; any output entry is rejected before register writes or stream start until mixed return framing and Stream-Out buffers are implemented.
- `eStreamStart()`'s actual scan rate, rather than the requested rate, is used for result timing.
- Every flat element is assigned `scan_index / actual_scan_rate + scan_position_offset`. T4/T7 offsets come from the documented auto-settling tables for the configured range/resolution/rate region; T8 AIN offsets are simultaneous. Explicit offsets are required where the manuals do not close the acquisition schedule.
- `Stream` performs this reconstruction internally once, then passes the resulting array into channel splitting. Flat data and `interleaved_sample_times_s` are exposed alongside the mapping from channel name to voltage array `V` and time array `t`. `-9999.0` placeholders become `NaN` without removing their timeline positions.

The actual-rate and time-axis defects are covered by device-free tests. Exact final-block duration and the already-running-event-loop contract remain unresolved in `known-issues.md`.

## Unified-stream implementation and deferred output boundary

The operation boundary is one LabJack stream session, not separately started Stream-In and Stream-Out objects. T-Series permits input-only, output-only, and combined input-output scan lists while allowing only one active stream session per device.

- `_stream.py` / `Stream` owns the complete ordered plan, configuration, single `eStreamStart()`/`eStreamStop()` lifecycle, and current input results. `LabJackDevice.stream()` is the sole public facade; the pre-release `stream_in()` method, `StreamIn` alias, aggregate-sampling-rate conversion helper, and direct legacy `Stream(...)` constructor have been removed.
- Periodic and aperiodic Stream-Out execution is deliberately deferred. Do not introduce a separate operation that attempts to start a second stream, and do not broaden current support before fake-LJM tests reproduce mixed-stream return framing.
- Keep `_stream_sample_times.py` free of In/Out ownership in its filename. It currently reconstructs input sample times, but it should evolve toward the full scan schedule from which input acquisition times and output update times can be projected. Rename it only if a more accurate shared schedule name is chosen during the unified refactor.
- One scan processes every ordered scan-list address, but output positions do not yield valid `eStreamRead()` values. `_StreamPlan` keeps total scan addresses, returned input addresses, and Stream-Out addresses as distinct counts and ordered mappings.
- Stream-Out support is capability-based, not a generic mode available on every register or physical channel. Input and output entries require validation against the exact device's streamable-register and target lists.

Analog roles are fixed: AIN registers are stream inputs, while analog stream output targets are DAC0 and DAC1. Digital I/O is physically bidirectional but direction-controlled; DIO state and DIO extended-feature registers can be stream inputs, while Stream-Out targets the FIO/EIO/CIO/MIO state or direction bank registers. A DIO line is input or driven output at a given instant, and changing direction during stream is an ordered hardware operation requiring explicit safety validation. T-Series exposes at most four Stream-Out engines; T4/T7 allow output-only stream, while T8 requires at least one AIN.

### Stream action terminology (planned pre-release correction)

Three concepts must not share one `in`/`out` field:

| Layer | Required vocabulary | Meaning |
| --- | --- | --- |
| Pythonic stream-plan action | `read` / `write` | What the `Stream` operation schedules for an ordered entry. |
| Physical channel capability/direction | `input` / `output` | What AIN, DAC, or a configured DIO line physically is or does. |
| LabJack/LJM mechanism | Stream-In, Stream-Out, `STREAM_OUT#`, `eStreamRead()` | Exact vendor terminology and primitive names, retained where technically required. |

The current public grouped keys `inputs`/`outputs`, ordered-entry
`mode`/`direction="in"|"out"`, `_StreamChannel.direction`, and corresponding
input/output properties and counts conflate these layers. They remain the
implemented API until one synchronized source/test/documentation refactor
resolves `STREAM-009`; do not present the proposed spelling as implemented.

The target public vocabulary is grouped `read=...` / `write=...`, ordered
`action="read"|"write"`, and `read_config` / `write_config`. The corresponding
normalized type should be an ordered `_StreamEntry` with an `action`, not a
physical `_StreamChannel` with a `direction`. Read/write entries and counts
should follow the same vocabulary. Hardware-specific fields may still use
`direction="input"|"output"` where direction is real configuration, especially
for DIO. Vendor-facing documentation and compiler code continue to call the
buffer engines Stream-Out and their scan-list addresses `STREAM_OUT#`; a
streamed write is not an `eWrite*()` call per scan.

### Unified stream API input forms (implemented normalization)

`LabJackDevice.stream()` provides both of these mutually exclusive forms and normalizes either one into the same internal ordered `_StreamPlan`:

1. A grouped convenience form with `inputs=...` and `outputs=...`, each carrying its direction-common defaults and channel entries. Python cannot use `in=` as an ordinary keyword argument because `in` is reserved. Its deterministic order is listed inputs followed by listed outputs; use the ordered form for phase-sensitive interleaving.
2. An explicitly ordered `channels=[...]` sequence whose entries carry a channel/target, `mode="in"` or `mode="out"`, and entry-specific settings. This is the lossless **plan** form for interleaved In/Out timing, repeated input addresses, and distinct occurrences of the same address. The current result mapping is still keyed by channel name and cannot preserve distinct results for duplicates; see `STREAM-008`. A channel-keyed mapping is not canonical because it cannot represent duplicates and makes insertion order an implicit hardware-timing contract.

The implemented shapes are:

```python
device.stream(
    scan_rate_Hz=1_000,
    duration_s=10,
    inputs={
        "resolution_index": 1,
        "settling_us": 0,
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

device.stream(
    scan_rate_Hz=1_000,
    duration_s=10,
    input_config={"resolution_index": 1, "settling_us": 0},
    output_config={"playback": "periodic"},
    channels=[
        {"channel": "AIN0", "mode": "in", "range_V": 10.0},
        {"channel": "DAC0", "mode": "out", "data": waveform},
        {"channel": "AIN1", "direction": "in", "range_V": 10.0},
    ],
)
```

`mode` and `direction` are accepted synonyms per ordered entry, but an entry
cannot provide both. Grouped order is all listed inputs followed by all listed
outputs; phase-sensitive interleaving uses the ordered form. Entry values
override direction-common values. Output examples above document plan shape,
not executable support: they currently raise `NotImplementedError` before any
device configuration.

Configuration ownership must remain layered rather than flattening every option into each entry:

- session-wide: scan rate, duration or scan count, trigger/clock behavior, and full scan ordering;
- input-common: read block sizing/result policy and stream-wide AIN resolution/settling defaults;
- output-common: default playback/buffer/allocation policy when implemented;
- input entry: input register plus register-family settings such as AIN range/negative channel or DIO/EF configuration;
- output entry: physical target, waveform/data source, periodic or aperiodic mode, and target-specific settings such as DAC units or DIO direction/state policy.

Output entries name physical targets such as `DAC0` or `DIO2`; ordinary users should not allocate `STREAM_OUT#` indices. When implemented, the internal compiler will allocate at most four engines, map DAC targets directly, group/encode compatible DIO targets into bank state words and inhibit masks, and preserve the ordered scan event represented by each `STREAM_OUT#`. The current executor raises `NotImplementedError` for every output entry. It also rejects non-AIN inputs, non-GND negative channels, and mixed per-channel AIN ranges rather than applying an incomplete timing/configuration model.

## Settling advisory contract

- `Stream` emits settling guidance before it configures or starts a stream. The guidance is derived only from existing stream settings and model-specific published tables; source resistance is deliberately not a new input or inferred value. For T-Series stream, the setting named in the message is the scan-list-wide `STREAM_SETTLING_US`. Concrete registers such as `AIN2_SETTLING_US` are channel-specific command-response settings; documentation uses `AINn_SETTLING_US` or `AIN#_SETTLING_US` only as a channel-number pattern.
- The message tells users conditionally what settling may be needed at published source-resistance reference points. The user remains responsible for knowing the connected source, topology, voltage steps, and required accuracy.
- A positive manual configuration below the exact T7 Table 1 Auto baseline is a warning. Otherwise, source-resistance guidance is informational and must not be described as validation of the actual circuit. Acquisition schedules that cannot fit the requested scan period are rejected by the separate sample-time resolver.
- Settling guidance is one compact line: `<tag>: STREAM_SETTLING_US value (currently <setting>) may need to be increased depending on source resistance; <source-resistance point>: <suggested settling>; ...`. It does not repeat the scan-list channels or explain the setting's global scope on every invocation; that belongs in documentation. Semicolons delimit table points, and no explicit newline is inserted. Published settling values are starting delays, so a needed increase is written with `≥`, not `≤`; an `OS` point states precisely that 1 second failed absolute accuracy rather than extrapolating untested behavior above 1 second.
- Other multiline operational messages may use the general tagged-block format established for the project: the first line begins `<tag>: ` and each continuation line is indented by the exact character width of that prefix. For example, continuation lines following `INFO: ` begin with six spaces. This remains a general formatting rule rather than an INFO-specific formatter.
- The protected reusable formatter lives in `labjack_device.py`; unrelated legacy `print()` calls have not been migrated. The stream-specific resolver, table constants, and result type live with their only consumer in `_stream.py` and are absent from package exports.

## Imports and public API

The canonical import path is now:

```python
from pylabjack import LabJackDevice, LabJackDeviceTypeEnum, ReadWrite, Stream
```

Modules use relative internal imports, and `tests/test_package.py` verifies the installed package in Python isolated mode. `test_labjack_device.ipynb` uses explicit `pylabjack` and NumPy imports and requires the user to replace all-capital placeholders before its hardware cells are run. Do not add root compatibility shims or execute the notebook as automated validation.

Sample-time reconstruction is not a standalone public API. The acquisition-
schedule types and reconstruction function live in the protected
`_stream_sample_times` module and are absent from `pylabjack.__all__`. Users
obtain times from the `Stream` result, primarily through
`records[channel]["t"]` or `interleaved_sample_times_s`.

`SoftwareProvenance` and its capture functions live in the protected
`_software_provenance` module and are not package exports. Users receive the
immutable value through `LabJackDevice.software_provenance` and every operation
object’s `software_provenance` property.

`ReadWrite` and `LabJackReadWriteError` are public package exports. The
normalized command/result dataclasses and normalization functions remain in
the protected `_read_write` module; users receive entries from a completed
operation rather than constructing the backend directly.

`LabJackDeviceTypeEnum` in `_ljm_aux.py` is the single device-family authority
for the facade and its internal operations. It includes T4, T7, T8, DIGIT, U3,
U6, UE9, and U12. Membership is taxonomy, not a promise that every operation or
backend supports the model: the current LJM connection path is T-Series-only,
while the private sample-time resolver can still model documented U-family
acquisition schedules independently.

## External requirements observed in source

- Python 3.11 (the declared project range is `>=3.11,<3.12`).
- `labjack-ljm` 1.23.x, imported as `labjack.ljm`, plus the separately installed native LJM runtime for native calls.
- NumPy `>=1.26.4,<2.5` for streamed data storage and processing.
- Matplotlib and IPython kernel support only through the optional `notebook` dependency group.
- Git is optional and used only for checkout provenance; its absence does not block package import, connection, or operations.
- A supported LabJack device and connection for integration testing.

The lock reviewed on 2026-08-28 resolves Python 3.11.15, `labjack-ljm` 1.23.0, NumPy 2.4.6, and pytest 9.1.1 for the default development environment. No supported LabJack device/firmware matrix is declared yet.
