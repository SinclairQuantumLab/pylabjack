# Hardware safety runbook

Last safety review: 2026-08-30

LabJack calls can change process-global LJM configuration, persistent or power-up device state, trigger extended-feature registers, analog input configuration, and active streams. A successful connection is not permission to make all of those changes.

## Authorization boundary

Hardware access is allowed only when the user has asked for a real-device action and the target is unambiguous. Before the first call, establish:

- exact LabJack model and, when relevant, hardware/firmware version;
- connection type and user-supplied identifier;
- channel list and electrical setup;
- requested sampling and scan rates, duration, ranges, and negative-channel configuration;
- trigger channel, edge/mode, finite timeout, and a cancellation plan;
- registers and LJM library settings allowed to change;
- whether prior device state must be captured and restored;
- where results may be written and whether they may be retained.

If any missing item could change the target device or electrical behavior, stop and ask rather than using values from a demo, notebook, stored output, or previous session.

Checked-in hardware examples must not contain a usable device identifier. The
facade and stream modules take only the three device-selection values
positionally, and
`test_labjack_device.ipynb` uses all-capital placeholders such as
`<DEVICE_IDENTIFIER>`. Supplying those values makes a path executable; it does
not itself authorize an agent to run it. The stream module's fixed acquisition
settings are illustrative defaults, not authorization or proof that those
channels, rates, ranges, and register writes are safe for a selected device.

## Before access

1. Re-check `git status` and keep generated measurements outside tracked source paths.
2. Verify the exact model supports every planned register, rate, and trigger feature.
3. List all write calls that the operation will make, including implicit helper behavior and process-global LJM settings.
4. Detect an existing connection or active stream without stopping or replacing it unless that disruption was authorized.
5. Prefer a short, finite, low-rate initial read with no trigger and no unrelated register changes.
6. Choose the connection lifetime before access: use `with LabJackDevice(...)`
   for bounded work, or retain one device for repeated on-demand operations and
   put its public `close()` in the outermost applicable `finally` block.

## During access

- Never substitute one model for another because an example happens to connect.
- Do not use indefinite triggered waits by default.
- Keep blocking I/O off an application event loop unless the API explicitly provides and tests that contract.
- Track whether open/start/write operations actually succeeded so cleanup occurs exactly once.
- Preserve the original exception if stopping or closing also fails.
- Keep ownership boundaries intact: `LabJackDevice` closes its handle; an
  operation such as `Stream` stops only the stream session it started and never
  disconnects the longer-lived device.
- Avoid printing full arrays or identifiers to logs. Summarize counts, shapes, timing, and skipped samples.

## On-demand read/write boundary

- `read()`, `write()`, and `read_write()` are hardware-active synchronous
  operations. Before an authorized call, enumerate every write frame in exact
  order and verify each named register against the selected model and current
  electrical configuration.
- The implemented scalar backend calls `ljm.eNames()` once and changes only
  registers explicitly represented by write commands. It does not apply the
  unrelated AIN defaults still present in the older `configure_register()`
  path. Do not broaden the scalar operation with implicit setup writes.
- Multiple frames preserve order, but command-response timing is not a stream:
  do not describe reads as simultaneous or assign reconstructed per-frame
  timestamps. Only the host-observed whole-call timing is retained.
- Current support is one finite numeric value per named register. Numeric
  arrays, strings, byte arrays, and address/type calls require explicit future
  variants and model/register validation; do not infer them from input shape.
- No physical read or write has been validated in this repository. Fake-LJM
  framing tests establish software behavior only and do not authorize hardware
  access.

## Stream timing evidence

- Use the actual scan rate returned by the driver, not only the requested rate.
- Preserve dummy/skipped elements in their original flat positions; replacing a sentinel with `NaN` is safe, deleting it shifts every later timestamp.
- Treat the profiles in `docs/stream-sample-times.md` as manual-derived acquisition schedules, not proof that a connected high-impedance source has settled to the required accuracy.
- The implemented pre-stream settling advice is conditional: it summarizes exact T7 source-resistance reference points from published tables, but it does not accept or infer the connected source resistance or claim that an actual circuit has settled. T-Series stream advice names the scan-list-wide `STREAM_SETTLING_US`, not a channel-specific command-response register such as `AIN2_SETTLING_US`; published suggested delays are expressed as `≥` starting points, while `OS` is reported as “1 s failed absolute accuracy” without extrapolation. See `docs/stream-settling-advice.md` before changing its scope or severity rules.
- Automatic T4/T7/T8 AIN timing may use the documented model profile. Manual settling, mixed ranges, or non-AIN scan positions require an explicit complete interchannel delay or per-position offsets; do not add settling to a tabulated complete delay a second time.
- Do not use the current `Stream` executor for `STREAM_OUT#`, output-only, combined stream-in-out, non-AIN inputs, mixed AIN ranges, or non-GND negative channels. The unified plan represents input/output order and separate counts, but the executor deliberately rejects those configurations until the missing compilation and packed-return behavior is implemented; see `STREAM-007`.
- Consult `docs/stream-capabilities.md` before treating any LabJack/LJM stream feature as implemented. Vendor capability, enum membership, plan normalization, or timestamp calculation alone does not authorize device execution. The ledger's T4/T7/T8 boundary is device-free only until a precise model/firmware configuration is explicitly authorized and tested.
- Timestamp externally clocked scans from captured/per-scan start times. A nominal average scan rate cannot recover irregular trigger intervals.
- When hardware verification is authorized, compare the resolved offsets with the device timing output appropriate to that model and record model, firmware, scan list order, actual scan rate, range, resolution, settling, and clock source.

## Cleanup and handoff

1. Stop a stream that this run successfully started.
2. Disable or restore trigger extended-feature configuration changed by this run.
3. Restore device registers and process-global LJM settings when restoration was part of the plan.
4. Close every handle opened by this run exactly once through its owning
   `LabJackDevice`. A successful repeated `close()` is harmless; if `ljm.close()`
   fails, closure is unconfirmed and the current implementation retains the
   handle for a reported, deliberate retry.
5. Report cleanup failures and all state intentionally left changed.
6. Record enough environment and device metadata to reproduce the result without committing a usable identifier or secret.

The connection lifetime contract is covered by fake-LJM tests, but the open
stream-worker/stop cleanup defects in `STREAM-004`, trigger safety gaps, and
missing hardware validation still prevent treating the complete runbook as
automatically satisfied. Real-device work requires the authorization and
manual supervision above.
