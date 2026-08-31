# Stream sample-time reconstruction

This document defines how `pylabjack` reconstructs the acquisition time of
every element in a flat, interleaved LabJack stream. The private implementation
is in `pylabjack._stream_sample_times` and is used by `Stream` while it builds
the user-facing result. It is not a standalone public API.

The default output is device-clock-relative elapsed time, not the host time at
which `eStreamRead` returned and not a timestamp read from the device.

## Reconstruction contract

For the currently supported all-AIN input scan list of length $N$, flat element
$m$ belongs to:

$$
k = \left\lfloor \frac{m}{N} \right\rfloor,
\qquad
j = m \bmod N
$$

where $k$ is the scan index and $j$ is the position in the scan list. For an
internally clocked stream, its reconstructed sample time is:

$$
t_m = t_0 + \frac{k}{f_{\mathrm{scan,actual}}} + \delta_j
$$

`actual_scan_rate_hz` must be the rate returned when the stream starts. The
requested rate can differ slightly because the device clock has finite
resolution. This is the rate contract described in the LabJack
[Stream Scan Timing page, “Actual Scan Rate” subsection](https://support.labjack.com/docs/stream-scan-timing)
and, for LJM, the
[eStreamStart guide, `ScanRate` parameter](https://support.labjack.com/docs/estreamstart-ljm-user-s-guide).

The offsets $\delta_j$ describe physical acquisition order within one scan:

- Sequential devices normally use $\delta_j=j d_{\mathrm{interchannel}}$.
- T8 AIN positions use $\delta_j=0$ because they are sampled simultaneously.
- U12 stream/burst positions use $\delta_j=j/(Nf_{\mathrm{scan}})$ because its
  samples are evenly spaced rather than clustered near scan start.
- An explicit per-position offset vector can represent mixed or otherwise
  undocumented scan lists without inventing a timing rule.

LabJack describes T4/T7 interchannel delay as fixed with little jitter and
explicitly recommends accounting for it in phase-sensitive software in
[T-Series Appendix A-1-1, “Interchannel Delay - T4/T7”](https://support.labjack.com/docs/a-1-1-stream-data-rates-t-series-datasheet).
The same section defines a scan as one reading of every address and gives
`ScanRate = SampleRate / NumAddresses`.

### Time origin

Datasheet profiles set $\delta_0=0$, so `time_origin_s=0` means “the first
scan-list element was acquired at elapsed time zero.” It does **not** claim that
the first ADC conversion occurred at the scan-start interrupt. Appendix A-1-1
gives an example where the first T7 sample occurs about 5 us after scan start,
but it does not publish a universal first-sample offset for all configurations.

The internal reconstructor can instead use explicit position offsets and a
caller-selected time origin when a scan-start-referenced or externally anchored
timeline is available. For T-Series hardware,
[Section 3.2.1, “Channel-to-Channel Timing” and “Device Clock Scan Time”](https://support.labjack.com/docs/3-2-1-stream-timing-t-series-datasheet)
defines the SPC edges and the scan-index time calculation.

## User-facing result

```python
stream = device.stream(
    scan_rate_Hz=1_000.0,
    duration_s=1.0,
    inputs={"channels": ["AIN0", "AIN1"]},
)

ain0_times_s = stream.records["AIN0"]["t"]
all_sample_times_s = stream.interleaved_sample_times_s
```

`Stream` performs reconstruction automatically for its current LJM-supported
T4/T7/T8 AIN streams. Its relevant public results are:

- `actual_scan_rate_Hz`: the value returned by `eStreamStart`;
- `actual_sampling_rate_Hz`: actual scan rate times `num_input_addresses`;
- `actual_scan_address_rate_Hz`: actual scan rate times the full
  `num_scan_addresses` (identical for the current all-input executor);
- `interleaved_data`: the flat stream after skipped sentinels become `NaN`;
- `interleaved_sample_times_s`: the flat sample-time array;
- `records[channel]["t"]`: the corresponding per-channel slice.

The acquisition-schedule resolver, global element indices, and
reconstruction function are implementation details. They intentionally are not
exported from `pylabjack`.

## Model profiles and dependencies

The implementation uses the repository's existing `LabJackDeviceTypeEnum` as
its sole device-family authority. Profiles cover T4, T7, T8, U3, U6, UE9, and
U12; DIGIT has no supported analog-input schedule. Enum membership and a
device-independent acquisition profile do not imply that the current LJM
connection backend can operate every family. `Stream` currently connects
through LJM and therefore applies profiles automatically only to T4/T7/T8.
The U3/U6/UE9 numeric enum values follow the official LabJackPython
[`LJ_dtUE9`, `LJ_dtU3`, and `LJ_dtU6` declarations](https://github.com/labjack/LabJackPython/blob/a2f13eb548cca6416b1d44b08b63f7c5fd7f943b/src/LabJackPython.py#L3226-L3228),
and U12 follows the same repository's
[`devType = 1` USB discovery code](https://github.com/labjack/LabJackPython/blob/a2f13eb548cca6416b1d44b08b63f7c5fd7f943b/src/u12.py#L489).

All tabulated interchannel delays below are typical datasheet values. A
resolved profile records this in `values_are_typical`. Explicit overrides are
marked as caller-supplied rather than typical. The resolved
`configured_settling_us` is the value requested by the caller: zero denotes
automatic settling on devices where zero is the auto selector, not a physical
claim that the firmware waited zero microseconds.

### T4

T4 stream resolution index 0 resolves to index 1. The implementation uses
[T-Series Appendix A-1-1, Table A.1.6, “T4 Stream: Typical noise and interchannel delay”](https://support.labjack.com/docs/a-1-1-stream-data-rates-t-series-datasheet):

| Stream resolution index | Interchannel delay |
| ---: | ---: |
| 1 | 40 us at aggregate rate <= 20 ksample/s; 13 us above 20 ksample/s |
| 2 | 47 us |
| 3 | 121 us |
| 4 | 230 us |
| 5 | 446 us |

The rate threshold uses `actual_scan_rate_hz * num_addresses`. Table A.1.5 on
the same page gives channel-count-dependent maximum scan rates; the acquisition-
schedule resolver additionally rejects any derived last-channel offset that
reaches the next scan period.

The published table is for auto settling. A positive `settling_us` therefore
requires `interchannel_delay_s` or `channel_offsets_s`; the code does not assume
an undocumented conversion-overhead formula.

### T7 and T7-Pro

T7 stream resolution index 0 resolves to index 1. T7-Pro uses the same
high-speed converter in stream mode; high-resolution indices 9-12 are not
supported in stream, as stated in
[T-Series Section 3.2, “Configuring AIN for Stream”](https://support.labjack.com/docs/3-2-stream-mode-t-series-datasheet).

The implementation copies the supported entries from
[T-Series Appendix A-1-1, Table A.1.8, “T7 Stream: Typical noise and interchannel delay”](https://support.labjack.com/docs/a-1-1-stream-data-rates-t-series-datasheet):

| Half-range | Resolution indices and delays |
| --- | --- |
| ±10 V | RI1: 15 us at <=60 ksample/s, otherwise 8 us; RI2-8: 25, 45, 90, 170, 335, 670, 1335 us |
| ±1 V | RI1-8: 210, 220, 545, 585, 1200, 2415, 2750, 3415 us |
| ±0.1 V | RI1-2: 1040, 2105 us |
| ±0.01 V | multi-address stream combinations are not supported in Table A.1.8 |

Here `input_range_v` is the positive half-range (`10.0`, `1.0`, `0.1`, or
`0.01`), not the full peak-to-peak span. Table A.1.7 on that page gives the
supported maximum scan rates for every range/resolution/channel-count example.

`STREAM_SETTLING_US=0` selects automatic settling. The physical operation is
documented in the
[Analog Input Settling Time app note, “T7 Sampling Details”](https://support.labjack.com/docs/analog-input-settling-time-app-note):
the mux changes, the configured settling interval passes, and a resolution-
dependent number of ADC conversions is acquired. Because Table A.1.8 gives the
complete interchannel delay only for auto settling, a positive manual settling
value requires an explicit delay or offset vector. Settling is not added a
second time to a Table A.1.8 delay.

### T8

For an all-AIN scan list, every position receives the same within-scan offset.
[T-Series Section 3.2, “Simultaneous Sampling” and “Stream Data Framing”](https://support.labjack.com/docs/3-2-stream-mode-t-series-datasheet)
identifies T8 as the T-Series device that samples analog inputs simultaneously.
[Appendix A-1-1, Table A.1.9 and its following note](https://support.labjack.com/docs/a-1-1-stream-data-rates-t-series-datasheet)
states that T8 scan rate does not depend on the number of AIN addresses and that
T8 has no interchannel delay.

This zero-offset rule is limited to AIN capture. A mixed scan list containing
digital, capture, or stream-out addresses must supply explicit offsets unless a
separate documented timing rule is added.

### U3-LV and U3-HV

The implementation uses
[U3 Datasheet Section 3.2, Table 3.2-1, “Streaming at Various Resolutions”](https://support.labjack.com/docs/3-2-stream-mode-u3-datasheet):

| Low-level index | Explicit UD index | Maximum aggregate rate | Interchannel delay |
| ---: | ---: | ---: | ---: |
| 0 | 100 | 2.5 ksample/s | 320 us |
| 1 | 101 | 10 ksample/s | 82 us |
| 2 | 102 | 20 ksample/s | 42 us |
| 3 | 103 | 50 ksample/s | 12.5 us |

In the internal profile model, `resolution_index=None` means UD automatic
selection: choose the highest resolution whose maximum rate can sustain
`actual_scan_rate_hz * num_addresses`. Values 0-3 mean low-level indices and
100-103 mean explicit UD indices, avoiding the ambiguity that UD index 0 means
“automatic” while low-level index 0 is an actual hardware mode.

U3 low-level
[StreamConfig, U3 `ScanConfig` and `ScanInterval` fields](https://support.labjack.com/docs/streamconfig)
defines the resolution bits and scan interval. It has no stream settling field;
U3 `LongSettling` belongs to command-response AIN behavior, so nonzero
`settling_us` is not inferred for a U3 stream.

### U6 and U6-Pro

U6 stream index 0 resolves to index 1. U6-Pro high-resolution converter indices
9-12 are not available in stream mode. These rules and the complete automatic-
settling delay matrix come from
[U6 Datasheet Section 3.2, Table 3.2.2, “Stream performance characteristics” and note 4](https://support.labjack.com/docs/3-2-stream-mode-u6-datasheet):

| Half-range | RI1-8 interchannel delays |
| --- | --- |
| ±10 V | 15, 30, 40, 110, 220, 440, 875, 1740 us |
| ±1 V | 205, 220, 545, 600, 1210, 2430, 2880, 3740 us |
| ±0.1 V | 1010, 2030, 2560, 2630, 2730, 2940, 3380, 4240 us |
| ±0.01 V | 2500, 2535, 2560, 2630, 2730, 2940, 3380, 4240 us |

[Low-level StreamConfig, U6 `SettlingFactor` field](https://support.labjack.com/docs/streamconfig)
states that zero selects the minimum based on gain/resolution and nonzero values
specify settling in 10 us increments. The datasheet does not publish the
remaining conversion/pipeline term needed to turn every nonzero factor into a
complete interchannel delay, so manual settling requires an explicit override.

### UE9 and UE9-Pro

The low-level UE9 stream supports resolution values 12-16; values 0-12 resolve
to 12-bit timing. UE9-Pro's alternate high-resolution converter is not
supported by this stream command, as stated under
[Low-level StreamConfig, UE9 `Resolution` field](https://support.labjack.com/docs/streamconfig).

Base delays come from the
[UE9 Datasheet Appendix A, Analog Inputs table, “Channel-to-Channel Delay” rows and note 11](https://support.labjack.com/docs/appendix-a-specifications-ue9-datasheet):

| Stream resolution | Base interchannel delay |
| ---: | ---: |
| 12 bit | 12 us |
| 13 bit | 44 us |
| 14 bit | 158 us |
| 15 bit | 670 us |
| 16 bit | 2700 us |

UE9 is the one supported family for which the manual supplies an additive rule:
[UE9 Datasheet Section 2.7, opening AIN overview](https://support.labjack.com/docs/2-7-ain-ue9-datasheet)
says the settling parameter adds an approximate delay of its value times 5 us.
Pass that already-converted physical delay as `settling_us`; the resolver adds
it to the Appendix A base delay. For example, low-level factor 2 is
`settling_us=10.0`.

### U12

U12 is deliberately different. The
[U12 Datasheet Appendix D, “Channel-To-Channel Delay” paragraph](https://support.labjack.com/docs/appendix-d-maximum-data-rates-for-the-labjack-u12-)
states that all stream/burst samples are evenly spaced. For two channels at 500
scans/s, for example, the scan period is 2 ms and consecutive flat samples are
1 ms apart. Therefore:

$$
d_{\mathrm{interchannel}} = \frac{1}{N f_{\mathrm{scan,actual}}}
$$

This profile is formula-derived rather than a typical tabulated delay.

## Settling and interchannel delay are not additive synonyms

`settling_us` is the configured wait associated with mux settling.
`interchannel_delay_s` is the complete time between representative acquisition
times of adjacent scan positions. It can also include mux sequencing, ADC
acquisition/conversion, oversampling, and firmware pipeline time.

Consequently:

```text
sample-time offset = documented complete interchannel delay
```

is correct, while this generally is not:

```text
sample-time offset = table interchannel delay + settling again
```

The resolver follows three precedence levels:

1. `channel_offsets_s`: exact caller-supplied offset for every scan position;
2. `interchannel_delay_s`: caller-supplied uniform adjacent-element delay;
3. model tables/formulas: only when the documented configuration is complete.

The private resolver needs overrides for manual-settling T4/T7/U6 profiles,
mixed ranges, non-AIN T-Series scan lists, and unsupported configurations. The
current `Stream` executor is stricter: it rejects mixed ranges and non-AIN
inputs until the full ordered scan schedule can be compiled and projected into
the packed `eStreamRead()` input result. This is a deliberate refusal to turn
an undocumented assumption into a precise-looking sample time.

## Chunks, skipped scans, and external clocks

### Chunk boundaries

Low-level stream packets need not end on a complete scan. The private
reconstructor accepts the number of previously processed flat elements so it
can continue both the scan index and the within-scan phase correctly. The
current `Stream` path concatenates its read blocks before performing one
reconstruction.

### Skipped data

Do not delete `-9999.0` dummy elements before sample-time reconstruction.
T-Series
[Section 3.2.1, “Stream Timing Complications”](https://support.labjack.com/docs/3-2-1-stream-timing-t-series-datasheet)
explains that LJM inserts dummy values for skipped samples so timing positions
remain represented. U3/U6 similarly describe UD inserting `-9999.0` after
auto-recovery in their respective Section 3.2 pages. `Stream` converts the
value to `NaN` but leaves its sample time and array position intact.

### Irregular externally clocked scans

If scan starts are externally triggered at nonuniform intervals, a single scan
rate cannot reconstruct them. The private reconstructor can add the same
within-scan offsets to an explicit start time for each scan. `Stream` does not
currently expose such per-scan starts, so irregular external-clock sample times
are not recoverable through the public result from a value-only raw array.

## Validation scope

The model tables and sample-time arithmetic are covered by device-free tests.
They do not prove native-driver availability, firmware behavior, electrical
settling quality, or hardware operation. The reconstructor models when the
device is scheduled to sample; it does not assert that a high-impedance source
has reached the required analog accuracy by that instant.
