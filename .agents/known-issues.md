# Known issues and open decisions

Last source review: 2026-08-30

Unless noted otherwise, these observations come from static source review and have not been validated against a LabJack in this repository. Keep an issue open until a focused test demonstrates the intended contract.

## Resolved foundations

### PKG-001 — uv packaging and canonical import baseline (resolved 2026-08-28)

The project now uses `pyproject.toml`, `uv.lock`, Python 3.11, `uv_build`, and the `src/pylabjack` layout. Internal imports are relative, the stream facade uses `._stream`, and `pylabjack.__init__` explicitly exports the supported public surface. README examples use `from pylabjack import ...`.

Validation: `uv sync --locked`, three default pytest tests including a `python -I` installed-package import, and both sdist and wheel builds completed successfully. The renamed user-owned notebook now uses canonical imports, and no root compatibility shims were added.

### PROV-001 — Immutable package/Git operation provenance (resolved 2026-08-30)

The standard-library-only `_software_provenance.py` captures the installed package name/version plus a self-contained Git identity: local repository name, credential-free normalized `origin` repository identifier when present, full commit hash, worktree-dirty state, and explicit Git availability. It uses bounded noninteractive Git commands instead of parsing `.git` internals, caches one immutable value per process/source path, and treats absent Git/distribution metadata as data rather than an operation failure. `LabJackDevice` stores the snapshot before connecting, and `Stream` shares the exact same object. Branch/head-ref is deliberately omitted because it is a mutable label and does not improve commit identification or retrieval.

Validation: device-free tests cover frozen values, cache identity, package/Git absence, installed-wheel path isolation, full-hash normalization, credential/query/transport stripping, rejection of local or malformed remotes, missing `origin`, and actual temporary Git worktrees for clean/ignored, staged, unstaged, deleted, and untracked states. Fake-LJM lifecycle, read/write, and stream tests verify device capture and operation sharing. The locked 122-test suite and both package builds pass, and wheel/sdist inspection confirms that the resolver module is packaged. No native LJM or physical hardware access was used.

### RW-001 — Unified scalar numeric command-response operation (resolved 2026-08-30)

`LabJackDevice.read()`, `write()`, and `read_write()` now all return one `ReadWrite` operation object and execute through one ordered `ljm.eNames()` backend. Easy reads accept one name or an ordered sequence; easy writes accept one name/value or an ordered sequence of pairs; the advanced facade accepts ordered mapping or compact read/write commands. Normalization preserves duplicates and mixed hardware order, validates before device access, and compiles one numeric value per frame. The result retains the original request, immutable commands/aligned results, effective LJM arrays, read/write convenience values, UTC/monotonic whole-call host timing, immutable device identity, and the shared software provenance snapshot. No per-frame timestamp, simultaneity, or deterministic-spacing claim is made.

Validation: fake-LJM tests cover one-call framing, mapping/tuple commands, mixed ordering, duplicate names, defensive original-input copies, aligned immutable results, scalar/multiple convenience behavior, invalid names/actions/shapes/values, disconnected devices, exception chaining, return-length mismatch, concise string output, host timing boundaries, device identity, and provenance sharing. The locked 122-test suite and wheel/sdist builds pass, and archive inspection confirms `_read_write.py` plus its public documentation are packaged. The locally installed `labjack-ljm` 1.23 wrapper signature and source were inspected, but the separate native LJM DLL was unavailable and no physical read/write was performed.

### STREAM-003 — Per-element stream time axes (resolved 2026-08-29)

The flat-index/scan-rate formula was replaced with an explicit scan grid plus within-scan acquisition schedule in the private `pylabjack._stream_sample_times` module. `Stream` now captures the actual rate returned by `eStreamStart()`, preserves one sample time per flat element, uses documented auto-settling profiles for T4/T7 AIN, assigns simultaneous offsets to T8 AIN, and accepts explicit timing overrides for configurations the manuals do not fully specify. The resolver and facade share the existing `LabJackDeviceTypeEnum`, now extended with U3/U6/UE9/U12 rather than duplicating the device taxonomy. The internal resolver covers their documented schedules without claiming that the current LJM connection layer operates those devices; DIGIT remains unsupported for analog-input sample times. The configuration and reconstruction functions are intentionally absent from public package exports, and users receive reconstructed times through the `Stream` result.

Validation: device-free tests cover the T4/T7 tables and rate thresholds, T8 simultaneous samples, U3 automatic resolution selection, U6 tables, UE9 additive settling, U12 uniform sample spacing, rejection of non-enum and unsupported DIGIT types, partial chunks, irregular explicit scan starts, skipped placeholders, invalid overlap, per-channel spacing, manual-override boundaries, and a fake-LJM `eStreamStart()` actual-rate return. No native LJM or hardware timing check was run; datasheet-derived delays remain marked typical.

### STREAM-005 — Conditional T7 settling advisory (resolved 2026-08-29)

`Stream` now emits a compact settling advisory before register configuration and stream start. Its private resolver uses the existing `LabJackDeviceTypeEnum`, the configured scan list/range/resolution/settling, and exact T7 app-note Tables 1-2 rows. It deliberately has no source-resistance input, does not reuse T7 numbers for other models, does not interpolate missing RI rows, and reports `OS` only as “1 s failed absolute accuracy.” A protected tagged-message helper in `labjack_device.py` also aligns continuation lines by prefix width. Neither the resolver nor its result type is exported publicly.

Validation: device-free tests cover exact gain 10 / RI 1 Auto output, manual-warning severity, omission of already-satisfied numeric points, the over-50-ms software-settling marker, unavailable table rows, one-distinct-AIN behavior, non-T7 suppression, tagged multiline indentation, public-export boundaries, and message-before-register-write ordering through a fake device. No native LJM or hardware access was used; the advisory remains conditional rather than circuit validation.

### STREAM-006 — Unified stream ownership and safe input-only boundary (resolved 2026-08-29)

The former `StreamIn` implementation used one `_num_channels` value for the full scan list, valid returned inputs, timing, and records. A timing override could admit `STREAM_OUT#` and then misframe the padded LJM return. `_stream.py` now owns one `Stream` session, both public configuration forms normalize into one ordered `_StreamPlan`, and the plan has separate `num_scan_addresses`, `num_input_addresses`, and `num_output_addresses`. The pre-release `stream_in()` facade, `StreamIn` alias, aggregate-sampling-rate conversion helper, and direct legacy `Stream(...)` constructor have now been removed; `LabJackDevice.stream()` is the only public stream facade. Output entries, non-AIN inputs, mixed per-channel AIN ranges, and non-GND negative channels are rejected before device access rather than partially executed.

Validation: device-free plan tests cover grouped and explicitly ordered forms, mutual exclusion, preserved interleaved In/Out order, distinct counts, deferred-output rejection before device access, and mixed-range rejection. Package-boundary tests assert that `StreamIn` and `LabJackDevice.stream_in` are absent, and a constructor-signature test requires the protected normalized `_plan` path. The fake-LJM input test confirms the unified operation still uses the actual `eStreamStart()` rate. The full 65-test device-free suite and both package builds pass. No native LJM or hardware test was run.

### DOC-001 — Hardware examples use explicit inputs (resolved 2026-08-29)

`labjack_device.py` and `_stream.py` no longer contain a usable target. Their `__main__` blocks read device type, connection type, and identifier positionally and deliberately leave missing/invalid input errors unwrapped. The stream block is a fixed, untriggered demonstration over AIN0/AIN1/AIN4 at 10 kHz for 1 second, with 1000 scans/read, RI 1, auto settling, and ±10 V range, rather than a command-line acquisition interface. The user-owned `test_labjack_device.ipynb` uses canonical `pylabjack`/NumPy imports, the unified `stream()` API, and visibly all-capital placeholders for the device, connection, identifier, and AIN channels. README examples also use placeholders. All hardware paths remain opt-in and must not be used as smoke tests.

Validation: device-free static tests parse the notebook JSON, verify both modules' direct device-selection `sys.argv` contracts and the stream demo's fixed acquisition values, reject legacy notebook imports, and scan the maintained examples for literal IPv4 addresses. The notebook and module demos were not executed; no native LJM or hardware access was used.

### LIFE-001 — Deterministic device-handle ownership (resolved 2026-08-30)

`LabJackDevice` is now the sole owner of its LJM handle. Construction opens once,
publishes the handle only after device information is loaded successfully, and
rolls back a post-open initialization failure. The public idempotent `close()`
supports long-lived on-demand use, while `with LabJackDevice(...)` reuses that
same connection and closes it on exit. Operation objects such as `Stream` do not
disconnect the device. A body exception remains primary if close also fails;
the cleanup failure is attached as an exception note. `__del__()` remains only
a best-effort fallback.

Validation: fake-LJM device-free tests cover one open across repeated use,
explicit and context-managed close, repeated close, refusal to re-enter a
closed device, body/close exception precedence, retry after failed close, and
constructor rollback. Static hardware-example tests verify that the facade
demo uses a bounded context, the stream demo holds its connection through
`try`/`finally`, and the notebook uses explicit `close()`. No native LJM or
hardware access was used.

## Confirmed from source inspection

### RW-002 — Specialized register shapes and hardware validation are deferred

The implemented `ReadWrite` contract supports one finite numeric value per named register. Consecutive numeric arrays, strings, byte arrays, and address/type access need explicit operation variants or extensions with unambiguous inputs, result alignment, register/model validation, and fake-LJM call-signature tests. These LJM families describe register shape or addressing rather than repeated time-spaced sampling and must not be presented as Stream substitutes. No native-LJM execution or physical device validation exists yet for the scalar backend.

### REG-001 — Register writes include unrelated analog-input defaults

Every `configure_register()` call injects `AIN_ALL_NEGATIVE_CH=GND` and `AIN_ALL_RANGE=10.0`. Trigger setup and any otherwise narrow register write can therefore change all analog-input settings. The string branch also calls `eWriteNameString()` without the device handle expected by the LJM API.

Resolution needs explicit setup defaults separated from the generic writer plus call-signature tests for numeric and string values.

### STREAM-001 — Running-event-loop completion is unreliable

`Stream._run()` is declared async but performs blocking LJM calls and contains no effective await point. When a loop is already running, `_execute()` schedules a task without waiting; construction can return with `records is None`, and background task exceptions are not propagated.

Resolution requires an explicit synchronous/async API contract and tests in both execution contexts.

### STREAM-002 — Requested duration and returned data length can diverge

Scan count and read count are rounded upward. If an explicit `scans_per_read` does not divide the requested scan count, the final block is not trimmed to the requested scan count. Positive duration/rate/channel/read-size validation now occurs during plan normalization, but the returned-length contract remains unresolved.

Resolution needs a documented rounding contract and exact final-block truncation tests.

### STREAM-004 — Stream configuration and worker cleanup can hide failures

`Stream._configure()` catches all `LabJackRegisterConfigurationError` instances. It stops an active stream for error 2605 but does not retry the requested configuration; other register errors are not re-raised. Queue sentinel/join logic occurs after the read-loop cleanup, so an exception can leave the daemon worker waiting. A stop failure can replace the original read failure.

Resolution needs narrow exception handling, configuration retry/propagation, and structured worker/stream cleanup tests.

### STREAM-007 — Stream-Out and broader stream-input execution are deferred

LJM supports stream-in, stream-out, and combined stream-in-out in one stream session. The official `stream_basic_with_stream_out.py` example appends `STREAM_OUT0` to the same `eStreamStart()` scan list as AIN inputs. LJM returns a Python data list sized for `scansPerRead * totalScanAddresses`, but only the leading `scansPerRead * inputAddressCount` elements are valid; stream-out positions are omitted from the valid returned data.

The unified plan and public `inputs`/`outputs`/ordered `channels` syntax exist, but there is no engine allocator, target/buffer compiler, periodic or aperiodic refill lifecycle, DIO bank packing, mixed-scan input projection, or output-only execution. The current all-AIN executor also has one common AIN range and GND negative-channel implementation; it cannot yet compile mixed AIN settings or non-AIN input registers into a complete acquisition schedule.

Resolution requires compiling the existing plan into one LJM scan list, retaining the full schedule for input acquisition and output-update timing, projecting only valid packed input data into records, and supporting input-only, output-only, and combined sessions without starting multiple device streams. Add fake-LJM tests matching the official mixed-stream return framing before claiming support. No hardware test has been run.

### STREAM-008 — Repeated input addresses collide in the result mapping

The explicitly ordered stream plan preserves repeated input addresses and their scan-list positions, but `Stream._run()` assembles `records` as a dictionary keyed only by channel name. When the same input register occurs more than once, the later entry overwrites the earlier entry, so the public result cannot distinguish those occurrences even though the plan and flat data can.

Resolution requires a result representation with stable occurrence identity while preserving the existing unique-channel convenience contract, plus device-free tests for repeated and interleaved occurrences. Until then, repeated input addresses are plan-preserved but not supported as distinct structured results.

### STREAM-009 — Stream action and hardware direction use the same vocabulary

The public grouped form uses `inputs`/`outputs`; ordered entries accept
`mode="in"|"out"` or `direction="in"|"out"`; and `_StreamChannel.direction`
drives read-result versus future Stream-Out planning. This conflates three
different concepts: the action scheduled by the Python operation, the physical
input/output capability or configured DIO direction, and LabJack's exact
Stream-In/Stream-Out mechanism terminology.

The pre-release target is `read`/`write` for public and normalized stream-plan
actions, `input`/`output` only for physical capability or actual direction, and
unchanged vendor terms such as Stream-Out, `STREAM_OUT#`, and `eStreamRead()`
where those mechanisms are meant. The proposed public form uses grouped
`read=...`/`write=...`, ordered `action="read"|"write"`, and
`read_config`/`write_config`; `_StreamEntry.action` replaces
`_StreamChannel.direction`. A streamed write still compiles to a Stream-Out
engine rather than issuing one command-response `eWrite*()` per scan.

Resolution requires one synchronized pre-release refactor across facade
signatures, plan types and counts, parsing/errors, operation properties,
examples, README, the capability ledger, timestamp documentation, tests, and
the already-removed compatibility symbols. Until then, documentation must
distinguish the implemented input/output spelling from the planned read/write
contract.

### TRIGGER-001 — Trigger default and cancellation contract remain incomplete

`Stream` and both facade methods expose `trigger_timeout_s`, and `_configure_trigger()` converts seconds to integer milliseconds before writing `LJM_STREAM_RECEIVE_TIMEOUT_MS`. `None` still becomes zero, an indefinite wait, despite the repository safety policy preferring a finite default. Model support, cancellation, and cleanup behavior are not validated.

Validation: a device-free fake-device test verifies that `0.25` seconds is written as `250` milliseconds. No triggered hardware stream was run.

Resolution needs a finite public default, model support validation, cancellation behavior, and timeout/cleanup tests.

### AUX-001 — `LabJackStreamReturnEnum` does not define enum members

Its class body assigns to attributes on `ljm.constants` rather than binding names in the Enum. This creates no useful enum members and mutates the imported vendor namespace.

Other local cleanup debt includes mutable list defaults, mixed naming conventions, and TypedDicts that no current public contract uses.

### INFRA-001 — Verification and release infrastructure remains incomplete

uv metadata, dependency locking, Python support, package builds, a basic test suite, and `native_ljm`/`hardware` markers now exist. Remaining gaps are fake-LJM behavior tests, an actual native-runtime probe, supervised hardware tests, lint/type-check configuration, CI, a supported device/firmware matrix, license, changelog/version policy, and release/publishing workflow. `py.typed` is packaged, but no type checker currently validates that advertised inline typing. The repository-only `ljm_startup_configs.json` is not loaded or distributed, and its long-term role remains undecided.

## Runtime questions to confirm during fixes

- Verify the datasheet-derived timing profiles and requested-versus-actual rate behavior on explicitly authorized hardware before treating them as hardware-tested rather than device-free contract tests.
- Determine the exact stream-return length and backlog behavior for the final read before fixing truncation and reporting.
- Verify trigger support, valid registers, rate limits, and safe defaults per model rather than extrapolating the current T7-oriented examples.
- Measure memory use for long streams: the current path holds lists, NumPy arrays, channel copies, and deep copies concurrently.

## Open architectural decisions

- Whether and when to expand support beyond the currently declared Python 3.11 and `labjack-ljm` 1.23.x range.
- Supported LabJack device and firmware matrix.
- Synchronous-only API versus separate synchronous and asynchronous stream APIs.
- Whether `ljm_startup_configs.json` remains a versioned vendor reference or becomes an operational project configuration.
- Release target/version policy and the boundary between mock, native-runtime, and supervised hardware integration tests.
