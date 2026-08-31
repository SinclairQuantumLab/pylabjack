"""Plan and execute one LabJack stream session and assemble input results.

The executable backend currently supports internally clocked, all-AIN,
input-only T-Series plans with one common AIN range and GND-referenced inputs.
It uses LJM to resolve the scan list, start/read/stop the stream, reconstructs
element-aligned sample times from the actual scan rate, and emits conditional
T7 settling guidance.

The unified plan can represent ordered Stream-In and Stream-Out entries, but
periodic/aperiodic Stream-Out, output-only or combined execution, non-AIN
inputs, mixed AIN ranges, differential inputs, and an external scan clock are
not implemented. Unsupported executable plans are rejected rather than run
partially. U3/U6/UE9/U12 schedule calculations in ``_stream_sample_times`` do
not imply that this LJM executor supports those devices.

``LabJackDevice.stream()`` is the only public stream facade. The operation
constructor accepts only the normalized private plan supplied by that facade;
there is no ``stream_in()`` method, ``StreamIn`` alias, or direct aggregate-rate
compatibility constructor. Each result also retains immutable device-identity
and package/Git provenance snapshots captured by its owning device.

See ``docs/stream-capabilities.md`` for the maintained LJM-function,
device-family, channel, timing, result, and validation status ledger. Current
execution claims are device-free unless that ledger explicitly says otherwise.
"""

from labjack import ljm
from ._ljm_aux import (
    LabJackConnectionTypeEnum,
    LabJackDeviceTypeEnum,
    LabJackRegisterConfigurationError,
    LabJackStreamReadError,
    LabJackTriggerEdgeEnum,
    LabJackTriggerModeEnum,
    LabJackaData2chData,
)
from .labjack_device import (
    LabJackDevice,
    LabJackDeviceIdentity,
    _print_tagged_message,
)
from ._software_provenance import SoftwareProvenance
from ._stream_sample_times import (
    ResolvedAcquisitionSchedule,
    StreamSampleTimeConfig,
    StreamSampleTimes,
    reconstruct_stream_sample_times,
    resolve_acquisition_schedule,
)

import asyncio
import threading
import queue

import numpy as np
from datetime import datetime
from copy import deepcopy
import warnings
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import math
import sys
from typing import Any


_AUTO = "AUTO"
_OUT_OF_SPEC = "OS"
_SOURCE_RESISTANCE_OHM = (1_000, 10_000, 100_000, 1_000_000)
_T7_RANGE_TO_GAIN = {
    10.0: 1,
    1.0: 10,
    0.1: 100,
    0.01: 1000,
}

# Analog Input Settling Time app note, Table 1. T7 stream does not support
# high-resolution converter indices 9-12, so only exact stream rows are kept.
_T7_AUTO_SETTLING_US = {
    1: {1: 10.0, 4: 10.0, 8: 10.0},
    10: {1: 200.0, 4: 500.0, 8: 2_000.0},
    100: {1: 1_000.0, 4: 5_000.0, 8: 10_000.0},
    1000: {1: 5_000.0, 4: 5_000.0, 8: 10_000.0},
}

# Analog Input Settling Time app note, Table 2. Numeric values are suggested
# settling times in microseconds; AUTO refers to the corresponding Table 1 row;
# OS means a one-second settling time failed the absolute-accuracy specification.
_T7_SOURCE_RESISTANCE_SETTLING = {
    1: {
        1: (_AUTO, _AUTO, 100.0, 5_000.0),
        4: (_AUTO, _AUTO, 500.0, 250_000.0),
        8: (_AUTO, _AUTO, _AUTO, _OUT_OF_SPEC),
    },
    10: {
        1: (_AUTO, 1_000.0, 5_000.0, _OUT_OF_SPEC),
        4: (_AUTO, _AUTO, 10_000.0, 1_000_000.0),
        8: (_AUTO, _AUTO, _OUT_OF_SPEC, _OUT_OF_SPEC),
    },
    100: {
        1: (_AUTO, _OUT_OF_SPEC, _OUT_OF_SPEC, _OUT_OF_SPEC),
        4: (_AUTO, _OUT_OF_SPEC, _OUT_OF_SPEC, _OUT_OF_SPEC),
        8: (_AUTO, _OUT_OF_SPEC, _OUT_OF_SPEC, _OUT_OF_SPEC),
    },
    1000: {
        1: (_AUTO, _OUT_OF_SPEC, _OUT_OF_SPEC, _OUT_OF_SPEC),
        4: (_AUTO, _OUT_OF_SPEC, _OUT_OF_SPEC, _OUT_OF_SPEC),
        8: (_AUTO, _OUT_OF_SPEC, _OUT_OF_SPEC, _OUT_OF_SPEC),
    },
}


@dataclass(frozen=True, slots=True)
class _StreamSettlingAdvice:
    """A single internal message to emit before stream register writes."""

    tag: str
    message: str


@dataclass(frozen=True, slots=True)
class _StreamChannel:
    """One ordered scan-list entry after public configuration normalization."""

    channel: str
    direction: str
    range_v: float | None = None
    negative_channel: str | None = None
    playback: str | None = None
    data: Any = None


@dataclass(frozen=True, slots=True)
class _StreamPlan:
    """Complete normalized configuration for one device stream session."""

    entries: tuple[_StreamChannel, ...]
    duration_s: float
    scan_rate_hz: float
    scans_per_read: int | None
    resolution_index: int
    settling_us: float
    interchannel_delay_s: float | None
    channel_time_offsets_s: tuple[float, ...] | None
    do_trigger: bool
    trigger_channel: str
    trigger_mode: LabJackTriggerModeEnum
    trigger_edge: LabJackTriggerEdgeEnum
    trigger_timeout_s: float | None

    @property
    def input_entries(self) -> tuple[_StreamChannel, ...]:
        return tuple(entry for entry in self.entries if entry.direction == "in")

    @property
    def output_entries(self) -> tuple[_StreamChannel, ...]:
        return tuple(entry for entry in self.entries if entry.direction == "out")

    @property
    def num_scan_addresses(self) -> int:
        return len(self.entries)

    @property
    def num_input_addresses(self) -> int:
        return len(self.input_entries)

    @property
    def num_output_addresses(self) -> int:
        return len(self.output_entries)


def _format_duration_us(value_us: float) -> str:
    if value_us >= 1_000_000.0 and value_us % 1_000_000.0 == 0.0:
        return f"{value_us / 1_000_000.0:g} s"
    if value_us >= 1_000.0 and value_us % 1_000.0 == 0.0:
        return f"{value_us / 1_000.0:g} ms"
    return f"{value_us:g} µs"


def _format_resistance_ohm(value_ohm: int) -> str:
    if value_ohm >= 1_000_000 and value_ohm % 1_000_000 == 0:
        return f"{value_ohm // 1_000_000} MΩ"
    if value_ohm >= 1_000 and value_ohm % 1_000 == 0:
        return f"{value_ohm // 1_000} kΩ"
    return f"{value_ohm} Ω"


def _ain_channels(scan_channels: Sequence[str]) -> tuple[str, ...]:
    return tuple(
        dict.fromkeys(
            channel.upper()
            for channel in scan_channels
            if channel.upper().startswith("AIN")
        )
    )


def _resolve_stream_settling_advice(
    *,
    device_type: LabJackDeviceTypeEnum,
    scan_channels: Sequence[str],
    input_range_v: float,
    resolution_index: int,
    settling_us: float,
) -> _StreamSettlingAdvice | None:
    """Resolve conditional T7 guidance from stream settings alone."""
    if device_type is not LabJackDeviceTypeEnum.T7:
        return None

    channels = _ain_channels(scan_channels)
    if not channels:
        return None

    configured_settling_us = float(settling_us)
    if not math.isfinite(configured_settling_us) or configured_settling_us < 0.0:
        raise ValueError("settling_us must be finite and non-negative.")

    resolved_resolution_index = 1 if resolution_index == 0 else int(resolution_index)
    gain = _T7_RANGE_TO_GAIN.get(float(input_range_v))

    if gain is None:
        configured_label = (
            "Auto"
            if configured_settling_us == 0.0
            else _format_duration_us(configured_settling_us)
        )
        return _StreamSettlingAdvice(
            "INFO",
            f"STREAM_SETTLING_US value (currently {configured_label}) has no "
            "exact T7 Tables 1-2 source-resistance row for half-range "
            f"±{float(input_range_v):g} V.",
        )

    auto_settling_us = _T7_AUTO_SETTLING_US[gain].get(resolved_resolution_index)
    table_row = _T7_SOURCE_RESISTANCE_SETTLING[gain].get(
        resolved_resolution_index
    )

    if configured_settling_us == 0.0:
        configured_label = (
            "Auto"
            if auto_settling_us is None
            else f"Auto ({_format_duration_us(auto_settling_us)})"
        )
    else:
        configured_label = _format_duration_us(configured_settling_us)

    if len(channels) == 1:
        return _StreamSettlingAdvice(
            "INFO",
            f"STREAM_SETTLING_US value (currently {configured_label}) has no "
            "multi-channel settling advisory because only one distinct AIN "
            "is scanned.",
        )

    if auto_settling_us is None or table_row is None:
        return _StreamSettlingAdvice(
            "INFO",
            f"STREAM_SETTLING_US value (currently {configured_label}) has no "
            "exact T7 Tables 1-2 source-resistance row for "
            f"gain {gain}, RI {resolved_resolution_index}.",
        )

    effective_settling_us = (
        auto_settling_us
        if configured_settling_us == 0.0
        else configured_settling_us
    )
    tag = "INFO"
    if configured_settling_us != 0.0 and configured_settling_us < auto_settling_us:
        tag = "WARNING"
        opening = (
            f"STREAM_SETTLING_US value (currently {configured_label}) is below "
            f"T7 Table 1 Auto ({_format_duration_us(auto_settling_us)}) and may "
            "need to be increased depending on source resistance"
        )
    else:
        opening = (
            f"STREAM_SETTLING_US value (currently {configured_label}) may need "
            "to be increased depending on source resistance"
        )

    clauses = [opening]
    for resistance_ohm, recommendation in zip(
        _SOURCE_RESISTANCE_OHM, table_row, strict=True
    ):
        resistance_label = _format_resistance_ohm(resistance_ohm)
        if recommendation == _OUT_OF_SPEC:
            clauses.append(f"{resistance_label}: 1 s failed absolute accuracy")
            continue

        required_us = (
            auto_settling_us if recommendation == _AUTO else float(recommendation)
        )
        if effective_settling_us >= required_us:
            continue

        requirement = (
            f"{resistance_label}: suggested ≥ {_format_duration_us(required_us)}"
        )
        if required_us > 50_000.0:
            requirement += " (software settling required)"
        clauses.append(requirement)

    if len(clauses) == 1:
        clauses[0] = (
            f"STREAM_SETTLING_US value (currently {configured_label}); T7 "
            "Table 2 suggests no increase through 1 MΩ"
        )

    return _StreamSettlingAdvice(tag, "; ".join(clauses) + ".")


_INPUT_CONFIG_KEYS = {
    "resolution_index",
    "settling_us",
    "scans_per_read",
    "range_V",
    "ain_range_V",
    "negative_channel",
    "interchannel_delay_s",
    "channel_time_offsets_s",
}
_INPUT_ENTRY_KEYS = {"channel", "range_V", "ain_range_V", "negative_channel"}
_OUTPUT_CONFIG_KEYS = {"playback"}
_OUTPUT_ENTRY_KEYS = {"channel", "data", "playback"}


def _require_mapping(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{label} must be a mapping.")
    return dict(value)


def _reject_unknown_keys(
    config: Mapping[str, Any], allowed: set[str], label: str
) -> None:
    unknown = set(config) - allowed
    if unknown:
        names = ", ".join(sorted(map(str, unknown)))
        raise ValueError(f"{label} contains unsupported keys: {names}.")


def _get_range_v(config: Mapping[str, Any], default: float) -> float:
    if "range_V" in config and "ain_range_V" in config:
        raise ValueError("Use either range_V or ain_range_V, not both.")
    value = config.get("range_V", config.get("ain_range_V", default))
    value = float(value)
    if not math.isfinite(value) or value <= 0.0:
        raise ValueError("AIN range must be finite and greater than zero.")
    return value


def _parse_input_entry(
    value: object,
    *,
    default_range_v: float,
    default_negative_channel: str,
    label: str,
) -> _StreamChannel:
    if isinstance(value, str):
        config: dict[str, Any] = {"channel": value}
    else:
        config = _require_mapping(value, label)
    _reject_unknown_keys(config, _INPUT_ENTRY_KEYS, label)
    if "channel" not in config:
        raise ValueError(f"{label} requires a channel.")
    channel = str(config["channel"]).strip()
    if not channel:
        raise ValueError(f"{label} channel must be non-empty.")
    negative_channel = str(
        config.get("negative_channel", default_negative_channel)
    ).strip()
    if not negative_channel:
        raise ValueError(f"{label} negative_channel must be non-empty.")
    return _StreamChannel(
        channel=channel,
        direction="in",
        range_v=_get_range_v(config, default_range_v),
        negative_channel=negative_channel,
    )


def _parse_output_entry(
    value: object, *, default_playback: str, label: str
) -> _StreamChannel:
    config = _require_mapping(value, label)
    _reject_unknown_keys(config, _OUTPUT_ENTRY_KEYS, label)
    missing = {key for key in ("channel", "data") if key not in config}
    if missing:
        names = ", ".join(sorted(missing))
        raise ValueError(f"{label} requires: {names}.")
    channel = str(config["channel"]).strip()
    if not channel:
        raise ValueError(f"{label} channel must be non-empty.")
    playback = str(config.get("playback", default_playback)).strip().lower()
    if playback not in {"periodic", "aperiodic"}:
        raise ValueError("output playback must be 'periodic' or 'aperiodic'.")
    return _StreamChannel(
        channel=channel,
        direction="out",
        playback=playback,
        data=config["data"],
    )


def _normalize_input_config(
    value: object | None, *, allow_channels: bool
) -> tuple[dict[str, Any], Sequence[object] | None]:
    config = {} if value is None else _require_mapping(value, "input configuration")
    allowed = _INPUT_CONFIG_KEYS | ({"channels"} if allow_channels else set())
    _reject_unknown_keys(config, allowed, "input configuration")
    raw_channels = config.pop("channels", None)
    if raw_channels is not None and (
        isinstance(raw_channels, (str, bytes))
        or not isinstance(raw_channels, Sequence)
    ):
        raise TypeError("input channels must be a sequence, not a string.")
    return config, raw_channels


def _normalize_output_config(
    value: object | None, *, allow_channels: bool
) -> tuple[dict[str, Any], Sequence[object] | None]:
    config = {} if value is None else _require_mapping(value, "output configuration")
    allowed = _OUTPUT_CONFIG_KEYS | ({"channels"} if allow_channels else set())
    _reject_unknown_keys(config, allowed, "output configuration")
    raw_channels = config.pop("channels", None)
    if raw_channels is not None and (
        isinstance(raw_channels, (str, bytes))
        or not isinstance(raw_channels, Sequence)
    ):
        raise TypeError("output channels must be a sequence, not a string.")
    return config, raw_channels


def _normalize_stream_plan(
    *,
    scan_rate_Hz: float,
    duration_s: float = 1.0,
    inputs: Mapping[str, Any] | None = None,
    outputs: Mapping[str, Any] | None = None,
    channels: Sequence[Mapping[str, Any]] | None = None,
    input_config: Mapping[str, Any] | None = None,
    output_config: Mapping[str, Any] | None = None,
    do_trigger: bool = False,
    trigger_channel: str = "DIO0",
    trigger_mode: LabJackTriggerModeEnum = LabJackTriggerModeEnum.ConditionalReset,
    trigger_edge: LabJackTriggerEdgeEnum = LabJackTriggerEdgeEnum.Rising,
    trigger_timeout_s: float | None = None,
) -> _StreamPlan:
    """Normalize either supported public configuration form into one plan."""
    scan_rate_hz = float(scan_rate_Hz)
    requested_duration_s = float(duration_s)
    if not math.isfinite(scan_rate_hz) or scan_rate_hz <= 0.0:
        raise ValueError("scan_rate_Hz must be finite and greater than zero.")
    if not math.isfinite(requested_duration_s) or requested_duration_s <= 0.0:
        raise ValueError("duration_s must be finite and greater than zero.")
    if trigger_timeout_s is not None:
        trigger_timeout_s = float(trigger_timeout_s)
        if not math.isfinite(trigger_timeout_s) or trigger_timeout_s <= 0.0:
            raise ValueError(
                "trigger_timeout_s must be finite and greater than zero, or None."
            )

    grouped_form = inputs is not None or outputs is not None
    ordered_form = (
        channels is not None
        or input_config is not None
        or output_config is not None
    )
    if grouped_form and ordered_form:
        raise ValueError(
            "Use either inputs/outputs or channels with input_config/output_config, "
            "not both configuration forms."
        )

    entries: list[_StreamChannel] = []
    if not grouped_form and not ordered_form:
        inputs = {"channels": ["AIN0", "AIN1", "AIN2"]}
        grouped_form = True

    if grouped_form:
        input_common, raw_inputs = _normalize_input_config(
            inputs, allow_channels=True
        )
        output_common, raw_outputs = _normalize_output_config(
            outputs, allow_channels=True
        )
        raw_inputs = () if raw_inputs is None else raw_inputs
        raw_outputs = () if raw_outputs is None else raw_outputs
        default_range_v = _get_range_v(input_common, 10.0)
        default_negative = str(input_common.get("negative_channel", "GND"))
        default_playback = str(output_common.get("playback", "periodic"))
        entries.extend(
            _parse_input_entry(
                value,
                default_range_v=default_range_v,
                default_negative_channel=default_negative,
                label=f"inputs.channels[{index}]",
            )
            for index, value in enumerate(raw_inputs)
        )
        entries.extend(
            _parse_output_entry(
                value,
                default_playback=default_playback,
                label=f"outputs.channels[{index}]",
            )
            for index, value in enumerate(raw_outputs)
        )
    else:
        if channels is None:
            raise ValueError(
                "channels is required with input_config/output_config."
            )
        if isinstance(channels, (str, bytes)) or not isinstance(channels, Sequence):
            raise TypeError("channels must be an ordered sequence of mappings.")
        input_common, _ = _normalize_input_config(
            input_config, allow_channels=False
        )
        output_common, _ = _normalize_output_config(
            output_config, allow_channels=False
        )
        default_range_v = _get_range_v(input_common, 10.0)
        default_negative = str(input_common.get("negative_channel", "GND"))
        default_playback = str(output_common.get("playback", "periodic"))
        for index, value in enumerate(channels):
            entry = _require_mapping(value, f"channels[{index}]")
            has_mode = "mode" in entry
            has_direction = "direction" in entry
            if has_mode and has_direction:
                raise ValueError(
                    f"channels[{index}] must use either mode or direction, not both."
                )
            if not has_mode and not has_direction:
                raise ValueError(
                    f"channels[{index}] requires mode='in'/'out' or direction."
                )
            direction = str(
                entry.pop("direction", entry.pop("mode", ""))
            ).strip().lower()
            if direction == "in":
                entries.append(
                    _parse_input_entry(
                        entry,
                        default_range_v=default_range_v,
                        default_negative_channel=default_negative,
                        label=f"channels[{index}]",
                    )
                )
            elif direction == "out":
                entries.append(
                    _parse_output_entry(
                        entry,
                        default_playback=default_playback,
                        label=f"channels[{index}]",
                    )
                )
            else:
                raise ValueError(
                    f"channels[{index}] direction must be 'in' or 'out'."
                )

    if not entries:
        raise ValueError("A stream requires at least one input or output channel.")

    resolution_index = input_common.get("resolution_index", 0)
    if isinstance(resolution_index, bool) or not isinstance(resolution_index, int):
        raise TypeError("resolution_index must be an integer.")
    settling_us = float(input_common.get("settling_us", 0.0))
    if not math.isfinite(settling_us) or settling_us < 0.0:
        raise ValueError("settling_us must be finite and non-negative.")
    scans_per_read = input_common.get("scans_per_read")
    if scans_per_read is not None and (
        isinstance(scans_per_read, bool)
        or not isinstance(scans_per_read, int)
        or scans_per_read <= 0
    ):
        raise ValueError("scans_per_read must be a positive integer or None.")
    interchannel_delay_s = input_common.get("interchannel_delay_s")
    if interchannel_delay_s is not None:
        interchannel_delay_s = float(interchannel_delay_s)
        if not math.isfinite(interchannel_delay_s) or interchannel_delay_s < 0.0:
            raise ValueError(
                "interchannel_delay_s must be finite and non-negative."
            )
    raw_offsets = input_common.get("channel_time_offsets_s")
    channel_time_offsets_s = (
        None if raw_offsets is None else tuple(float(value) for value in raw_offsets)
    )

    return _StreamPlan(
        entries=tuple(entries),
        duration_s=requested_duration_s,
        scan_rate_hz=scan_rate_hz,
        scans_per_read=scans_per_read,
        resolution_index=resolution_index,
        settling_us=settling_us,
        interchannel_delay_s=interchannel_delay_s,
        channel_time_offsets_s=channel_time_offsets_s,
        do_trigger=bool(do_trigger),
        trigger_channel=str(trigger_channel),
        trigger_mode=trigger_mode,
        trigger_edge=trigger_edge,
        trigger_timeout_s=trigger_timeout_s,
    )


def _validate_current_stream_support(plan: _StreamPlan) -> None:
    """Reject plans the current input-only execution backend cannot honor."""
    if plan.num_output_addresses:
        raise NotImplementedError(
            "Periodic and aperiodic Stream-Out execution is not implemented yet. "
            "The output entries remain part of the unified StreamPlan design."
        )
    if not plan.num_input_addresses:
        raise ValueError("The current stream backend requires at least one input.")
    if any(
        not entry.channel.upper().startswith("AIN")
        for entry in plan.input_entries
    ):
        raise NotImplementedError(
            "The current stream input backend supports AIN registers only."
        )
    input_ranges = {entry.range_v for entry in plan.input_entries}
    if len(input_ranges) != 1:
        raise NotImplementedError(
            "Per-channel AIN ranges require a mixed-range acquisition schedule "
            "and are not implemented yet."
        )
    if any(
        entry.negative_channel.upper() != "GND"
        for entry in plan.input_entries
        if entry.negative_channel is not None
    ):
        raise NotImplementedError(
            "Per-channel negative AIN channels are not implemented yet."
        )


class Stream:
    """One LabJack stream session and its input results.

    Construct this operation through :meth:`LabJackDevice.stream`. Current
    execution is limited to internally clocked, all-AIN input plans with one
    common range and GND negative input. See ``docs/stream-capabilities.md`` for
    the exact support boundary and known lifecycle/result limitations.
    """

    # Read-only properties
    # # input
    @property
    def scan_channels(self): return self._scan_channels
    @property
    def scan_list(self): return self._scan_list
    @property
    def input_channels(self): return self._input_channels
    @property
    def output_channels(self): return self._output_channels
    @property
    def num_scan_addresses(self): return self._num_scan_addresses
    @property
    def num_input_addresses(self): return self._num_input_addresses
    @property
    def num_output_addresses(self): return self._num_output_addresses
    @property
    def duration_input_s(self): return self._duration_input
    @property
    def sampling_rate_Hz(self): return self._sampling_rate
    @property
    def scan_rate_Hz(self): return self._scan_rate
    @property
    def scans_per_read(self): return self._scans_per_read
    @property
    def do_trigger(self): return self._do_trigger
    @property
    def trigger_channel(self): return self._trigger_channel
    @property
    def trigger_mode(self): return self._trigger_mode
    @property
    def trigger_edge(self): return self._trigger_edge
    @property
    def trigger_timeout_s(self): return self._trigger_timeout
    # #derived
    @property
    def duration_s(self): return self._duration
    @property
    def num_samples(self): return self._num_samples
    @property
    def num_scans(self): return self._num_scans
    @property
    def records(self): return self._records
    @property
    def skipped_samples(self): return self._skipped_samples
    @property
    def actual_scan_rate_Hz(self): return self._actual_scan_rate
    @property
    def actual_sampling_rate_Hz(self):
        if self._actual_scan_rate is None:
            return None
        return self._actual_scan_rate * self._num_input_addresses
    @property
    def actual_scan_address_rate_Hz(self):
        if self._actual_scan_rate is None:
            return None
        return self._actual_scan_rate * self._num_scan_addresses
    @property
    def stream_resolution_index(self): return self._stream_resolution_index
    @property
    def stream_settling_us(self): return self._stream_settling_us
    @property
    def ain_range_V(self): return self._ain_range_V
    @property
    def interleaved_data(self): return self._interleaved_data
    @property
    def software_provenance(self) -> SoftwareProvenance:
        return self._software_provenance
    @property
    def device_identity(self) -> LabJackDeviceIdentity:
        return self._device_identity
    @property
    def interleaved_sample_times_s(self):
        if self._sample_times is None:
            return None
        return self._sample_times.sample_times_s

    def __init__(
        self,
        device: LabJackDevice,
        *,
        _plan: _StreamPlan,
    ) -> None:
        _validate_current_stream_support(_plan)

        self._device = device
        self._software_provenance = device.software_provenance
        self._device_identity = device.device_identity
        self._handle = device._handle
        self._plan = _plan
        self._scan_list = [entry.channel for entry in _plan.entries]
        self._input_channels = [
            entry.channel for entry in _plan.input_entries
        ]
        self._output_channels = [
            entry.channel for entry in _plan.output_entries
        ]
        # Legacy name: current results contain only input channels.
        self._scan_channels = list(self._input_channels)
        self._num_scan_addresses = _plan.num_scan_addresses
        self._num_input_addresses = _plan.num_input_addresses
        self._num_output_addresses = _plan.num_output_addresses
        self._duration_input = _plan.duration_s
        self._scan_rate = _plan.scan_rate_hz
        self._sampling_rate = self._scan_rate * self._num_input_addresses
        self._actual_scan_rate: float | None = None
        self._stream_resolution_index = _plan.resolution_index
        self._stream_settling_us = _plan.settling_us
        self._ain_range_V = float(_plan.input_entries[0].range_v)
        self._interchannel_delay_override_s = _plan.interchannel_delay_s
        self._channel_time_offsets_override_s = _plan.channel_time_offsets_s
        self._acquisition_schedule: ResolvedAcquisitionSchedule | None = None
        self._settling_advice: _StreamSettlingAdvice | None = None
        self._sample_times: StreamSampleTimes | None = None
        self._interleaved_data: np.ndarray | None = None
        self._records = None
        self._skipped_samples = 0

        requested_schedule = StreamSampleTimeConfig(
            device_type=self._device.device_type,
            actual_scan_rate_hz=self._scan_rate,
            num_addresses=self._num_input_addresses,
            resolution_index=self._stream_resolution_index,
            input_range_v=self._ain_range_V,
            settling_us=self._stream_settling_us,
            interchannel_delay_s=self._interchannel_delay_override_s,
            channel_offsets_s=self._channel_time_offsets_override_s,
        )
        requested_acquisition_schedule = resolve_acquisition_schedule(
            requested_schedule
        )
        self._settling_advice = _resolve_stream_settling_advice(
            device_type=self._device.device_type,
            scan_channels=self._input_channels,
            input_range_v=self._ain_range_V,
            resolution_index=requested_acquisition_schedule.resolution_index,
            settling_us=self._stream_settling_us,
        )
        self._num_scans = int(np.ceil(self._scan_rate * self._duration_input))
        self._duration = self._num_scans / self._scan_rate
        self._num_samples = self._num_scans * self._num_input_addresses
        self._scans_per_read = (
            self._num_scans
            if _plan.scans_per_read is None
            else _plan.scans_per_read
        )
        self._num_reads = int(
            np.ceil(float(self._num_scans) / self._scans_per_read)
        )

        self._do_trigger = _plan.do_trigger
        self._trigger_channel = _plan.trigger_channel
        self._trigger_mode = _plan.trigger_mode
        self._trigger_edge = _plan.trigger_edge
        self._trigger_timeout = _plan.trigger_timeout_s

        if self._settling_advice is not None:
            _print_tagged_message(
                self._settling_advice.tag,
                self._settling_advice.message,
                flush=True,
            )

        self._configure()
        if self._do_trigger:
            self._configure_trigger()
        self._execute()


    def _configure(self) -> None:
        """
        Device configuration for streaming
        https://support.labjack.com/docs/3-2-stream-mode-t-series-datasheet#id-3.2StreamMode[T-SeriesDatasheet]-ConfiguringAINforStream
        """
        print(f">>> Configuring LabJack for streaming... ", end="")
        # register config for stream
        config_register = {
            # Ensure triggered stream is disabled initially.
            "STREAM_TRIGGER_INDEX": int(0),
            # Enable internally-clocked stream.
            "STREAM_CLOCK_SOURCE": int(0),
            # # settling time in microseconds
            # https://support.labjack.com/docs/analog-input-settling-time-app-note#AnalogInputSettlingTime(AppNote)-T7SamplingDetails
            "STREAM_SETTLING_US": self._stream_settling_us,
            # The resolution index for stream readings
            # under https://support.labjack.com/docs/a-3-analog-input-t-series-datasheet
            # e.g., https://support.labjack.com/docs/a-3-2-2-t7-noise-and-resolution-t-series-datasheet#A-3-2-2T7NoiseandResolution[T-SeriesDatasheet]-ADCNoiseandResolution
            "STREAM_RESOLUTION_INDEX": self._stream_resolution_index,
        }

        start = datetime.now()
        try:
            self._device.configure_register(
                AIN_ALL_RANGE=self._ain_range_V,
                **config_register,
            )
        except LabJackRegisterConfigurationError as ex:
            # op stream if stream was active
            # labjack.ljm.ljm.LJMError: LJM library error code 2605 STREAM_IS_ACTIVE
            if ex.__cause__ and \
                isinstance(ex.__cause__, ljm.LJMError) and \
                ex.__cause__.errorCode == 2605:
                warnings.warn("Stream was active. Attempting to stop stream... ", category='UserWarning')
                ljm.eStreamStop(self._handle)
                warnings.warn("Stream stopped.", category='UserWarning')
        end = datetime.now()
        td_exe = end - start
        print(f"Done. Execution time: {td_exe.total_seconds():.6f} s")
        print()


    def _configure_trigger(self) -> None:
        """
        Configure the device for trigger.
        """
        print(f">>> Configuring LabJack for trigger...", end="")

        start = datetime.now()
        # library config
        config_library_trigger = {
            ljm.constants.STREAM_SCANS_RETURN: ljm.constants.STREAM_SCANS_RETURN_ALL,
            ljm.constants.STREAM_RECEIVE_TIMEOUT_MS: (
                0
                if self._trigger_timeout is None
                else int(math.ceil(self._trigger_timeout * 1_000.0))
            ),
        }
        self._device.configure_library(**config_library_trigger)

        # register config
        # # Clear any previous settings on trigger channel's Extended Feature registers
        self._device.configure_register(**{f"{self._trigger_channel}_EF_ENABLE": 0})

        config_register_trigger = {}
        # # Get the address of the trigger channel
        address = ljm.nameToAddress(self._trigger_channel)[0]
        config_register_trigger["STREAM_TRIGGER_INDEX"] = address

        # # Pre-configure some trigger modes (Frequency In and Pulse Width In)
        config_register_trigger[f"{self._trigger_channel}_EF_INDEX"] = 3 # rising-to-rising edges
        config_register_trigger[f"{self._trigger_channel}_EF_INDEX"] = 4 # falling-to-falling edges

        if self._trigger_mode is LabJackTriggerModeEnum.FrequencyIn:
            ef_index = self._trigger_mode.value  # e.g., 3
            ef_index += 0 if self._trigger_edge is LabJackTriggerEdgeEnum.Rising else 1
            config_register_trigger[f"{self._trigger_channel}_EF_INDEX"] = ef_index

        if self._trigger_mode is LabJackTriggerModeEnum.PulseWidthIn:
            ef_index = self._trigger_mode.value  # e.g., 5
            # Note: The original code writes to EF_IDEX which may be a typo.
            config_register_trigger[f"{self._trigger_channel}_EF_INDEX"] = ef_index

        if self._trigger_mode is LabJackTriggerModeEnum.ConditionalReset:
            ef_index = self._trigger_mode.value  # e.g., 12
            config_register_trigger[f"{self._trigger_channel}_EF_INDEX"] = ef_index
            ef_config_a = self._trigger_edge.value
            config_register_trigger[f"{self._trigger_channel}_EF_CONFIG_A"] = ef_config_a

        self._device.configure_register(**config_register_trigger)

        # #  Enable the trigger
        self._device.configure_register(**{f"{self._trigger_channel}_EF_ENABLE": 1})

        end = datetime.now()
        td_exe = end - start

        print(f"Done. Execution time: {td_exe.total_seconds():.6f} s")
        print()


    def _stack_stream_reads(self,
                                  ir: int,
                                  timestamp_read_return: datetime,
                                  ret: tuple[list[float], int, int],
                                  ) -> None:
        """
        stack the return of each eStreamRead() to this instance.
        Intended to be asyncio.queue'd in _stream() method.
        """
        a_data = np.array(ret[0]) # stream data read
        device_scan_backlog = ret[1]
        ljm_scan_backlog = ret[2]

        # Count skipped samples (indicated by -9999 values)
        skipped_samples = np.sum(a_data == -9999.0)
        self._skipped_samples += skipped_samples

        # conver skipped samples to np.nan
        a_data[a_data == -9999.0] = np.nan

        # add stream data of current eStreamRead
        self._total_a_data.extend(a_data)

        # time that data was returned from eStreamRead
        self._timestamp_read_return[ir] = timestamp_read_return

        current_samples = len(a_data)
        self._samples += current_samples
        current_scans = int(current_samples / self._num_input_addresses)
        self._scans += current_scans

        msg = f"\teStreamRead {ir + 1} out of {self._num_reads} returned at {timestamp_read_return}."
        msg += f"\n\t\tScans Skipped across channels = {skipped_samples:0.0f}, "
        msg += f"Scan Backlogs: Device = {device_scan_backlog}, LJM = {ljm_scan_backlog}\n"
        print(msg, flush=True)

    def _queue_worker(self) -> None:
        while True:
            item = self._queue.get()
            if item is None:
                break  # signal to exit
            ir, timestamp_read_return, ret = item
            self._stack_stream_reads(ir, timestamp_read_return, ret)
            self._queue.task_done()

    async def _run(self) -> None:
        """
        Perform the stream reading and store the result in this instance.

        ljm methods used:
        - https://support.labjack.com/docs/namestoaddresses-ljm-user-s-guide
        - https://support.labjack.com/docs/estreamstart-ljm-user-s-guide
        - https://support.labjack.com/docs/estreamread-ljm-user-s-guide
        - https://support.labjack.com/docs/estreamstop-ljm-user-s-guide
        """

        handle = self._handle

        # Streaming configuration parameters
        scans_per_read = self._scans_per_read
        num_addresses = self._num_scan_addresses
        scan_list_addresses = ljm.namesToAddresses(
            self._num_scan_addresses, self._scan_list
        )[0]
        scan_rate = self._scan_rate
        num_reads = self._num_reads

        # Start streaming
        # wait for trigger before streaming if enabled
        print(f">>> Streaming starting... ", end="", flush=True)
        stream_started = False
        try:
            actual_scan_rate = ljm.eStreamStart(
                handle,
                scans_per_read,
                num_addresses,
                scan_list_addresses,
                scan_rate,
            )
            self._actual_scan_rate = float(actual_scan_rate)
            self._duration = self._num_scans / self._actual_scan_rate
            self._acquisition_schedule = resolve_acquisition_schedule(
                StreamSampleTimeConfig(
                    device_type=self._device.device_type,
                    actual_scan_rate_hz=self._actual_scan_rate,
                    num_addresses=self._num_input_addresses,
                    resolution_index=self._stream_resolution_index,
                    input_range_v=self._ain_range_V,
                    settling_us=self._stream_settling_us,
                    interchannel_delay_s=self._interchannel_delay_override_s,
                    channel_offsets_s=self._channel_time_offsets_override_s,
                )
            )
            stream_started = True  # set after successful eStreamStart()
        except ljm.LJMError as ljmex:
            raise LabJackStreamReadError("LabJack library-level error") from ljmex
        except Exception as ex:
            raise LabJackStreamReadError("Non LabJack library-level error") from ex
        finally:
            if stream_started is not True:
                # attempt to stop stream in case the device started streaming
                print("Stream failed to start. Attempting to stop stream... ", end="", flush=True)
                try:
                    ljm.eStreamStop(handle)
                except ljm.LJMError as ljmex:
                    print("Failed.", flush=True)
                    raise LabJackStreamReadError("LabJack library-level error") from ljmex
                except Exception as ex:
                    print("Failed.", flush=True)
                    raise LabJackStreamReadError("Non LabJack library-level error") from ex
                else:
                    print("Done.", flush=True)


        print(f"Started.", flush=True)

        if self._do_trigger:
            print("\tWaiting for trigger..."
                  "\n\tLabJack will start to stream once triggered (without letting you know).", flush=True)

        self._samples = 0
        self._scans = 0
        self._skipped_samples = 0
        self._total_a_data = []  # Accumulate data across reads
        self._timestamp_read_return = [None] * num_reads

        # Read stream data for the specified number of reads.
        self._queue = queue.Queue()
        worker_thread = threading.Thread(target=self._queue_worker, daemon=True)
        worker_thread.start()

        ir = 0
        try:
            while ir < num_reads:
                # read stream from LabJack
                try:
                    ret = ljm.eStreamRead(handle)
                    timestamp_read_return = datetime.now()
                except ljm.LJMError as ljmex:
                    # If no scans are returned, continue; otherwise, propagate the error.
                    if ljmex.errorCode == ljm.errorcodes.NO_SCANS_RETURNED:
                        continue
                    raise ljmex

                # stack the return of each eStreamRead() to this instance
                self._queue.put((ir, timestamp_read_return, ret))

                ir += 1

        except ljm.LJMError as ljmex:
            raise LabJackStreamReadError("LabJack library-level error") from ljmex
        except Exception as ex:
            raise LabJackStreamReadError("Non LabJack library-level error") from ex
        finally:
            # Stop the stream
            print(">>> Stopping Stream...\n", flush=True)
            try:
                ljm.eStreamStop(handle)
            except ljm.LJMError as ljmex:
                raise LabJackStreamReadError("LabJack library-level error") from ljmex
            except Exception as ex:
                raise LabJackStreamReadError("Non LabJack library-level error") from ex
            print("<<< Stream stopped.\n", flush=True)

        # wait until data stacking is done
        self._queue.put(None)  # signal to stop thread
        worker_thread.join()   # wait for worker to clean up

        msg = f"\t# scans = {self._samples} total, {self._scans}/channel"
        msg += f"\tSkipped scans across channels = {self._skipped_samples:0.0f}\n"
        print(msg, flush=True)

        # Process raw streamed data into channel-specific data.
        self._interleaved_data = np.asarray(self._total_a_data, dtype=float)
        if self._acquisition_schedule is None:
            raise LabJackStreamReadError("Stream completed without an acquisition schedule.")
        self._sample_times = reconstruct_stream_sample_times(
            self._interleaved_data,
            self._acquisition_schedule,
        )
        ch_data = LabJackaData2chData(
            self._interleaved_data,
            self._num_input_addresses,
            sample_times_s=self._sample_times.sample_times_s,
        )
        records = {}
        for inx, a_scan_list_name in enumerate(self._input_channels):
            ch_data_channel = deepcopy(ch_data[inx])
            ch_data_channel.pop('idx')
            records[a_scan_list_name] = ch_data_channel

        # store result to this instance
        self._records = records
        # self._records_ready.set()  # signal that records are ready


    def _execute(self) -> None:
        """Run from a script or schedule on an already-running event loop.

        The existing-loop completion contract remains unresolved; see
        ``STREAM-001`` in the repository's known issues.
        """
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            # No running loop: script mode
            asyncio.run(self._run())
        else:
            # Running loop (Jupyter, async app): schedule without waiting.
            loop.call_soon_threadsafe(
                lambda: asyncio.ensure_future(self._run())
            )

    def __str__(self) -> str:
        msg = "LabJack stream:"
        if self.records is None:
            msg += "\n\trecords = pending"
        else:
            msg += "\n\trecords:"
            for channel, record in self.records.items():
                values = record["V"]
                msg += (
                    f"\n\t\t{channel}: {values.size} samples, "
                    f"{np.count_nonzero(np.isnan(values))} skipped"
                )
        msg += f"\n\tduration = {self.duration_s} s"
        msg += f"\n\trequested sampling rate = {self.sampling_rate_Hz} total samples/s"
        msg += f"\n\trequested scan rate = {self.scan_rate_Hz} scans/s"
        msg += f"\n\tactual scan rate = {self.actual_scan_rate_Hz} scans/s"
        msg += f"\n\tactual aggregate sample rate = {self.actual_sampling_rate_Hz} samples/s"
        msg += (
            f"\n\tscan-list addresses = {self.num_scan_addresses} "
            f"({self.num_input_addresses} input, {self.num_output_addresses} output)"
        )
        msg += f"\n\ttriggered = {self.do_trigger}"
        if self._do_trigger:
            msg += f"\n\t\ttrigger channel = {self.trigger_channel}"
            msg += f"\n\t\ttrigger mode = {self.trigger_mode.name}"
            msg += f"\n\t\ttrigger edge = {self.trigger_edge.name}"
        return msg


if __name__ == "__main__":
    # Stream demo
    # uv run python -m pylabjack._stream <DEVICE_TYPE> <CONNECTION_TYPE> <DEVICE_IDENTIFIER>

    # parse arguments
    device_type = LabJackDeviceTypeEnum[sys.argv[1]]
    connection_type = LabJackConnectionTypeEnum[sys.argv[2]]
    device_identifier = sys.argv[3]

    # connect to device
    device = LabJackDevice(
        device_type=device_type,
        connection_type=connection_type,
        device_identifier=device_identifier,
    )

    try:
        # >>> stream >>>

        # scan settings
        # Verify their electrical and model-specific suitability for the device model
        scan_rate_Hz = 10_000.0
        duration_s = 1.0
        scans_per_read = 1_000
        resolution_index = 1
        settling_us = 0.0
        ain_range_V = 10.0
        input_channels = ["AIN0", "AIN1", "AIN4"]

        # perform streaming and return the results
        stream = device.stream(
            scan_rate_Hz=scan_rate_Hz,
            duration_s=duration_s,
            inputs={
                "scans_per_read": scans_per_read,
                "resolution_index": resolution_index,
                "settling_us": settling_us,
                "channels": [
                    {"channel": channel, "range_V": ain_range_V}
                    for channel in input_channels
                ],
            },
            do_trigger=False,
        )
        print(stream)
        print()
        total_skipped_samples = sum(
            np.isnan(record["V"]).sum()
            for record in stream.records.values()
        )
        print(f"Recounting skipped total samples = {total_skipped_samples}")

        # <<< stream <<<

    finally:
        # disconnect from device when the demo finishes or raises an exception
        device.close()
