# Stream capability and implementation status

Last source review: 2026-08-30

This is the maintained ledger for LabJack stream functionality that the
repository implements, represents, or has deliberately deferred. It separates
vendor capability from `pylabjack` capability: a feature appearing in a
LabJack manual, an enum, or an internal plan does not mean this library can
execute it.

The status words have strict meanings:

| Status | Meaning in this repository |
| --- | --- |
| **Implemented** | An execution or result path exists and has focused device-free tests. This does **not** mean it has been validated on physical hardware. |
| **Partial** | A usable subset exists, but an important safety, lifecycle, model-validation, or result-contract gap remains. |
| **Plan only** | Public input can be normalized into the unified ordered plan, but `Stream` rejects the plan before device access. |
| **Calculation only** | A device-independent schedule calculation exists, but the current LJM executor does not claim operational support for that device. |
| **Not implemented** | No supported operational path exists. |

This is a stream-scoped inventory, not an exhaustive catalog of every LJM
function or LabJack feature. Add a row when a capability enters the public
stream design, implementation, or a required dependency of either.

## Current executable boundary

The only current execution path is one internally clocked, input-only stream
whose scan-list entries are all AIN registers. All AINs must use one common
half-range and `GND` as the negative channel. The path is designed around the
T4, T7, and T8, but a complete device/firmware compatibility guard and physical
hardware matrix do not yet exist. Accordingly, even those three models are
**device-free verified, not hardware verified**.

Finishing a stream does not disconnect its `LabJackDevice`. Callers can perform
later operations through the same connection and close it explicitly when it
is no longer needed.

`LabJackDevice.stream()` accepts grouped `inputs`/`outputs` or one explicitly
ordered `channels` sequence. `_normalize_stream_plan()` preserves scan-list
order and separates total, input, and output address counts. Output entries can
therefore be expressed, but `_validate_current_stream_support()` raises
`NotImplementedError` before checking the device connection. This is
**Plan only**, not Stream-Out support.

The vendor model is broader. LabJack describes input-only, output-only, and
combined input/output operation as one device stream session in the
[T-Series Stream Mode overview, especially “Stream-Out”](https://support.labjack.com/docs/3-2-stream-mode-t-series-datasheet),
and its official
[`stream_basic_with_stream_out.py` example](https://github.com/labjack/labjack-ljm-python/blob/master/Examples/More/Stream/stream_basic_with_stream_out.py)
puts `STREAM_OUT0` in the same scan list as AIN inputs. `pylabjack` intentionally
does not start a second output stream.

## LJM primitive coverage

| LJM primitive | Vendor role | `pylabjack` status and exact boundary |
| --- | --- | --- |
| [`ljm.namesToAddresses()`](https://support.labjack.com/docs/namestoaddresses-ljm-user-s-guide) | Convert ordered register names to Modbus addresses. | **Implemented** in `Stream._run()` for the current all-AIN scan list. Broader streamable-register validation is not implemented. |
| [`ljm.eStreamStart()`](https://support.labjack.com/docs/estreamstart-ljm-user-s-guide) | Start the single stream session and return the actual scan rate. | **Implemented** for the current input-only boundary. The returned rate, not merely the request, drives duration and sample-time reconstruction. Output-only and combined scan lists are not executed. |
| [`ljm.eStreamRead()`](https://support.labjack.com/docs/estreamread-ljm-user-s-guide) | Return stream data and device/LJM backlog counts. | **Implemented** for all-input framing. `-9999.0` skipped samples become `NaN` without removing their time positions. Projection of valid input values from a mixed In/Out return is **Not implemented**; see `STREAM-007`. |
| [`ljm.eStreamStop()`](https://support.labjack.com/docs/estreamstop-ljm-user-s-guide) | Stop the active stream. | **Partial**. The normal read path and failed-start path attempt a stop, but stop/configuration/worker failures can still mask an earlier error or strand the worker; see `STREAM-004`. |
| [`ljm.nameToAddress()`](https://support.labjack.com/docs/nametoaddress-ljm-user-s-guide) | Resolve the trigger register address used as `STREAM_TRIGGER_INDEX`. | **Partial**, used by `_configure_trigger()`. Trigger-register and mode support is not validated per model; see `TRIGGER-001`. |
| [`ljm.eWriteNames()`](https://support.labjack.com/docs/ewritenames-ljm-user-s-guide) through `LabJackDevice.configure_register()` | Write stream-wide and trigger registers. | **Partial**. `_configure()` requests internal clock, resolution, settling, range, and trigger-disabled state. The generic writer currently injects unrelated AIN defaults, and its string path is defective; see `REG-001`. |
| [`ljm.writeLibraryConfigS()`](https://support.labjack.com/docs/writelibraryconfigs-ljm-user-s-guide) through `LabJackDevice.configure_library()` | Set process-global LJM stream-return and receive-timeout behavior. | **Partial**, currently used for triggered-stream return policy and seconds-to-milliseconds timeout conversion. `None` still selects an indefinite timeout and cancellation is unresolved; see `TRIGGER-001`. |
| [`ljm.periodicStreamOut()`](https://support.labjack.com/docs/periodicstreamout-ljm-user-s-guide) | Configure a periodically repeating Stream-Out waveform. | **Not implemented**. The public plan can retain `playback="periodic"` and `data`, but no engine, target, buffer, or scan-list compilation occurs. |
| [`ljm.initializeAperiodicStreamOut()`](https://support.labjack.com/docs/initializeaperiodicstreamout-ljm-user-s-guide) | Initialize an aperiodically refilled Stream-Out buffer. | **Not implemented**. `playback="aperiodic"` is syntax only. |
| [`ljm.writeAperiodicStreamOut()`](https://support.labjack.com/docs/writeaperiodicstreamout-ljm-user-s-guide) | Refill an aperiodic Stream-Out buffer while streaming. | **Not implemented**. There is no refill lifecycle, underflow policy, or cancellation contract. |

The low-level alternative described in the
[T-Series Stream-Out section, “Stream-Out Operation” and “Stream-Out Registers”](https://support.labjack.com/docs/3-2-3-stream-out-t-series-datasheet)
is also not implemented: no `STREAM_OUT#` allocator, target assignment, loop
size, buffer-status handling, or buffer writes exist.

## LabJack capability coverage

| LabJack stream capability | Vendor capability | Repository status |
| --- | --- | --- |
| T4/T7/T8 AIN Stream-In | AIN registers are streamable inputs under the [Stream Mode “Streamable Registers” and AIN configuration sections](https://support.labjack.com/docs/3-2-stream-mode-t-series-datasheet). | **Implemented** within the common-range, GND-referenced, internal-clock boundary. Tests fake LJM; no physical model/firmware combination has been validated. |
| Digital Stream-In (DI/DIO state) | T-Series stream lists can contain supported digital state or DIO extended-feature registers listed by the [Stream Mode “Streamable Registers” section](https://support.labjack.com/docs/3-2-stream-mode-t-series-datasheet). | **Plan only** at the generic-name level. Every input name not beginning with `AIN`, including DIO, is rejected before execution; direction/configuration and streamability are not validated. |
| Other non-AIN Stream-In | The same vendor table includes additional model-specific streamable registers. | **Plan only** at the generic-name level and **Not implemented** for execution, validation, timing, and structured results. |
| DAC Stream-Out | Stream-Out engines can target supported registers including DAC targets as described in [Stream-Out “Target Registers”](https://support.labjack.com/docs/3-2-3-stream-out-t-series-datasheet). | **Plan only**, and target names are not yet capability-validated. No waveform reaches DAC0 or DAC1. |
| Digital Stream-Out | DIO is direction-controlled and bank registers provide advanced state/direction writes; see [Digital I/O](https://support.labjack.com/docs/13-0-digital-i-o-t-series-datasheet) and [Advanced DIO Control, state/direction masks](https://support.labjack.com/docs/13-9-advanced-dio-control). | **Plan only** at the generic entry level. DIO bank packing, inhibit masks, direction safety, and target validation are **Not implemented**. |
| Four Stream-Out engines (`STREAM_OUT0`–`STREAM_OUT3`) | T-Series exposes four numbered engines and their register groups in [Stream-Out “Stream-Out Registers”](https://support.labjack.com/docs/3-2-3-stream-out-t-series-datasheet). | **Not implemented**. There is no allocator or protection against engine/target conflicts. |
| Output-only session | T4/T7 can run output-only; T8 Stream-Out requires at least one AIN in the scan list, as noted in the model limitations on the [T-Series Stream-Out page](https://support.labjack.com/docs/3-2-3-stream-out-t-series-datasheet). | **Plan only**. An output-only plan normalizes, then `Stream` rejects it before device access. |
| Combined input/output session | Vendor operation uses one interleaved scan list; the official combined example is linked above. | **Plan only**. Ordering and separate address counts exist, but engine compilation and mixed-return projection do not. |
| Periodic output | Repeating buffer playback through a Stream-Out engine. | **Plan only** syntax; execution is **Not implemented**. |
| Aperiodic output | Host-refilled buffer playback through a Stream-Out engine. | **Plan only** syntax; initialization/refill execution is **Not implemented**. |
| Internally clocked stream | `STREAM_CLOCK_SOURCE=0`; scan timing behavior is described in [T-Series Stream Timing, “Externally Clocked Stream” versus normal timing](https://support.labjack.com/docs/3-2-1-stream-timing-t-series-datasheet). | **Implemented**. `_configure()` always requests clock source 0. |
| External clock | Vendor special mode allows an external scan clock on supported hardware. | **Not implemented** by the public operation. Explicit scan-start arrays exist only in the private reconstruction function for device-free calculation/tests. |
| Triggered stream | Vendor triggered stream uses `STREAM_TRIGGER_INDEX` and LJM receive behavior. | **Partial**. EF setup, trigger index, return policy, and timeout conversion exist; finite default, exact per-model support, cancellation, and robust cleanup remain open in `TRIGGER-001`. |
| Per-channel AIN ranges | Hardware registers can configure channel ranges where the device supports them. | **Plan only** values are retained, but mixed ranges are rejected because execution and timing currently assume one `AIN_ALL_RANGE`. |
| Differential/non-GND AIN | Differential capability is model/channel specific; see [Analog Inputs, “Single-ended or Differential”](https://support.labjack.com/docs/14-0-analog-inputs-t-series-datasheet). | **Plan only** `negative_channel` input exists, but every non-`GND` value is rejected. |
| Repeated input address | LJM scan lists can be ordered, and the internal plan preserves repeated entries. | **Partial**. Execution can retain the repeated positions, but the final `records` mapping is keyed only by channel name, so duplicate names overwrite one another; see `STREAM-008`. |
| Model-specific scan-list/rate limits | Valid channels, scan rates, address rates, and resolution combinations depend on the exact model/configuration; the [Stream Mode page](https://support.labjack.com/docs/3-2-stream-mode-t-series-datasheet) routes to those limits. | **Not implemented** as a preflight matrix. The public plan checks only generic positivity/type constraints and otherwise relies on later resolver/LJM errors. |

Outside streaming, `LabJackDevice.read()` now provides generic scalar
command-response access through
[`ljm.eNames()`](https://support.labjack.com/docs/enames-ljm-user-s-guide), so a
caller may request a named DIO state register supported by the selected device.
This does not add DIO direction/configuration policy, model-specific register
validation, or physical-hardware validation. Streamed DI remains unimplemented
by the current all-AIN `Stream` executor.

## Device-family and timing coverage

This table distinguishes executable stream support from timestamp schedule
coverage. The timing formulas and their table-level sources are detailed in
[Stream sample-time reconstruction](stream-sample-times.md).

| Device family | Stream execution | Sample-time reconstruction | Settling advisory |
| --- | --- | --- | --- |
| T4 | **Implemented boundary**, device-free only; all-AIN/common-range/GND/internal-clock restrictions apply. | **Implemented** from the documented sequential/typical schedule, with explicit overrides for unresolved configurations. | **Not implemented**. |
| T7 | **Implemented boundary**, device-free only; the same restrictions apply. | **Implemented** from documented range/resolution/rate-dependent sequential/typical schedules. | **Implemented** for exact Analog Input Settling Time app-note Tables 1–2 rows; it does not accept or infer source resistance. |
| T8 | **Implemented boundary**, device-free only; exact register/model compatibility remains unverified on hardware. | **Implemented** with simultaneous within-scan AIN offsets. | **Not implemented**. |
| U3, U6, UE9, U12 | No execution support is claimed by the current `Stream` LJM backend. | **Calculation only** for the documented schedules in `_stream_sample_times.py`. | **Not implemented**. |
| DIGIT | The current executor accepts only AIN input, which does not define a meaningful DIGIT acquisition path. | Explicitly rejected for AIN sample-time reconstruction. | Not applicable. |

Enum membership is shared taxonomy, not an operation-support declaration.
`LabJackDeviceTypeEnum` must therefore remain broader than this table's
executable boundary.

## Configuration and result contract

| Contract | Status |
| --- | --- |
| One public `LabJackDevice.stream()` facade returning `Stream` | **Implemented**. The pre-release `stream_in()` method, `StreamIn` alias, aggregate-rate helper, and direct legacy constructor are removed. |
| Immutable software-provenance snapshot on `Stream` | **Implemented**. The operation shares its owning device's process-cached package/Git snapshot; unavailable Git metadata remains explicit rather than failing acquisition. |
| Immutable device-identity snapshot on `Stream` | **Implemented**. Type, connection, serial number, IP address, and port are retained independently of later connection close. |
| Grouped `inputs`/`outputs` and explicitly ordered `channels` forms | **Implemented normalization**; the forms are mutually exclusive. |
| Separate `num_scan_addresses`, `num_input_addresses`, and `num_output_addresses` | **Implemented** in the normalized plan and operation properties. |
| Stream-wide `STREAM_RESOLUTION_INDEX` and `STREAM_SETTLING_US` | **Implemented** as common AIN configuration and timing inputs; exact model/configuration support is not a complete preflight matrix. |
| Actual scan rate from `eStreamStart()` | **Implemented** and used for duration/timing. |
| Element-aligned flat timestamps and per-channel `t` arrays | **Implemented** for the current input boundary; values describe scheduled acquisition, not host return time or proof of electrical settling. |
| `-9999.0` skipped-sample preservation | **Implemented** as `NaN` with the timeline position retained. |
| T7 conditional settling message before register writes | **Implemented**; see [T7 stream settling advice](stream-settling-advice.md). |
| Exact requested-duration trimming | **Partial**; a final overfull read is not trimmed (`STREAM-002`). |
| Completion inside an already-running event loop | **Partial/unreliable**; the constructor can return before results exist (`STREAM-001`). |
| Deterministic stop/worker/error cleanup | **Partial** (`STREAM-004`). |
| Distinct result entries for repeated channel names | **Not implemented** (`STREAM-008`). |
| Native LJM and physical-hardware validation | **Not performed** in this repository. Default tests are device-free. |

## Maintenance contract

Any change to a stream-related LJM call, supported device, register/channel
class, clock or trigger mode, input/output mode, timing rule, or result shape
must update all affected rows here in the same change. Also synchronize:

- the module-level status summary in `src/pylabjack/_stream.py`;
- the short public pointer in `README.md`;
- `.agents/project-context.md` for ownership/data flow;
- `.agents/hardware-safety.md` and `.agents/known-issues.md` for safety or
  incomplete behavior; and
- focused device-free/fake-LJM tests that distinguish normalization from
  execution and hardware validation.

Do not promote a row from **Plan only**, **Calculation only**, or **Partial**
solely because the vendor supports it or a type can represent it. Promotion
requires an executable contract and corresponding tests; physical validation
must remain explicitly labeled until it is actually performed.
