# T7 stream settling advice

`Stream` prints one conditional analog-input settling message before it
writes stream registers or starts acquisition. This is a preflight reminder,
not an electrical measurement: `pylabjack` neither asks for nor infers source
resistance. The user remains responsible for the connected circuit, preceding
channel voltage step, required accuracy, and whether a longer delay is usable
at the requested rate.

The resolver lives with its only consumer in `pylabjack._stream` and is private
to `Stream`. It is not exported as a public calculator or configuration API.

## Which setting the message describes

T7 command-response reads can use a numbered `AINn_SETTLING_US` register, such
as `AIN2_SETTLING_US`. A stream instead uses the one scan-list-wide
`STREAM_SETTLING_US` setting for every streamed AIN. This distinction is stated
in the T7 datasheet's
[Section 14.3.0, “Settling” and “Streaming AIN” subsections](https://support.labjack.com/docs/14-3-0-analog-inputs-t7-t-series-datasheet):
the command-response settings are per AIN, while stream uses
`STREAM_SETTLING_US` and `STREAM_RESOLUTION_INDEX`.

Consequently, increasing settling to accommodate one high-impedance source
increases the settling applied to all AIN positions in that stream. At a high
scan rate, the complete scan still has to fit inside its scan period. The
LabJack app note's
[“Settling Tests,” Test B note](https://support.labjack.com/docs/analog-input-settling-time-app-note)
states that scan overlap occurs when the number of channels times settling time
exceeds the scan interval. `pylabjack` separately rejects a reconstructed
acquisition schedule whose last within-scan offset reaches the next scan.

## Inputs and table coverage

The advisory uses only values already supplied to `Stream`:

- device family;
- distinct streamed AIN names;
- common AIN half-range, which determines T7 gain;
- resolved stream resolution index;
- `STREAM_SETTLING_US`, where zero means Auto.

Exact numeric guidance is currently limited to T7/T7-Pro configurations that
have rows in the LabJack
[Analog Input Settling Time app note, Table 1 and Table 2](https://support.labjack.com/docs/analog-input-settling-time-app-note).
That app note labels its measured results T7-specific, while saying the general
concepts apply to T4, U6, and UE9. `pylabjack` therefore does not copy T7
numbers to T4, T8, or U-series devices.

The implemented T7 matrix is:

- gains 1, 10, 100, and 1000, corresponding to half-ranges ±10 V, ±1 V,
  ±0.1 V, and ±0.01 V;
- stream resolution indices 1, 4, and 8, the exact rows shared by app-note
  Tables 1-2;
- source-resistance reference points 1 kΩ, 10 kΩ, 100 kΩ, and 1 MΩ.

Resolution index 0 is reported using the T7 stream default, RI 1. Other valid
stream indices are not interpolated: the message states that no exact table row
exists and prints no invented resistance-dependent value.

Table 1 supplies the Auto settling duration for a gain/resolution pair. Table 2
supplies a suggested settling duration at each resistance point. A Table 2
`Auto` entry resolves to the matching Table 1 duration. A Table 2 `OS` entry is
reported only as `1 s failed absolute accuracy`, matching the app note's note
immediately below Table 2; it is not extrapolated into a claim about delays
greater than one second.

The app note's
[paragraph immediately after Table 2 footnote 2](https://support.labjack.com/docs/analog-input-settling-time-app-note)
says settling above 50 ms must be implemented in software and describes taking
two same-channel readings around a software delay. Recommendations over 50 ms
are therefore marked `software settling required`.

## Severity and compact format

The output is a single line:

```text
TAG: STREAM_SETTLING_US value (currently setting) may need to be increased depending on source resistance; resistance point: result; ...
```

- `INFO` means the current configuration is at least the Table 1 Auto value;
  the remaining clauses show only resistance points that may require more
  delay, plus every applicable out-of-spec point.
- `WARNING` means a positive manual setting is below the Table 1 Auto value.
- Suggested delays use `≥` because they are minimum starting values from the
  published table, never upper bounds.
- No explicit newline is embedded in this advisory. The shared protected
  tagged-message formatter nevertheless supports multiline operational
  messages by indenting each continuation line by the prefix width: six spaces
  after `INFO: `, nine after `WARNING: `.

For example, gain 10, RI 1, Auto, and scan list `AIN0, AIN2` produces:

```text
INFO: STREAM_SETTLING_US value (currently Auto (200 µs)) may need to be increased depending on source resistance; 10 kΩ: suggested ≥ 1 ms; 100 kΩ: suggested ≥ 5 ms; 1 MΩ: 1 s failed absolute accuracy.
```

The omitted 1 kΩ point is already covered by Auto in Table 2. If a manual
setting were only 100 µs, the same configuration would be a `WARNING` and the
1 kΩ point would appear as `suggested ≥ 200 µs`.

## Single-channel and unsupported cases

The app note's
[Test A, “Impact of Source Resistance and Channel-to-Channel Voltage Change”](https://support.labjack.com/docs/analog-input-settling-time-app-note)
attributes the dynamic error to multiplexer switching and the voltage change
between successive channels. When the scan list contains only one distinct AIN,
the message explains that this multichannel table guidance is not applicable.
Repeated appearances of the same AIN still count as one distinct source.

No numeric message is emitted for non-T7 device families. A T7 configuration
without an exact range or RI row receives an informational scope/coverage
message instead of extrapolated values. A scan list without AIN positions has
no analog settling advisory.

## What the advisory cannot establish

The published table is a finite set of measured reference points, not a circuit
model. The message does not establish:

- the actual source impedance or RC time constant;
- the voltage difference from the preceding scan-list channel;
- settling of sensors, amplifiers, filters, multiplexers, or wiring outside the
  LabJack;
- absolute accuracy at a resistance between or beyond the published points;
- native LJM availability, firmware behavior, or success on connected hardware.

The app note's
[“T7 Sampling Details” section](https://support.labjack.com/docs/analog-input-settling-time-app-note)
describes the physical sequence as mux change, settling interval, and one or
more ADC samples; the preceding “Analog Input Dynamic Response” section and
Figure 7 explain the source-resistance and preceding-voltage-step dependence.
Neither quantity is observable from the stream configuration. Treat the message
as a prompt for an informed circuit-level decision, not as a pass/fail verdict.
