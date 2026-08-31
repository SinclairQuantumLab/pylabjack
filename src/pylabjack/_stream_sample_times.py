"""Internal sample-time reconstruction for LabJack stream data.

The implementation separates the scan clock from the within-scan acquisition
schedule. It never derives sample times from host read-return times and is not
part of the package's public API.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import isclose
from typing import Sequence

import numpy as np

from ._ljm_aux import LabJackDeviceTypeEnum


class StreamSampleTimeError(ValueError):
    """Raised when a physical sample time cannot be reconstructed safely."""


@dataclass(frozen=True, slots=True)
class StreamSampleTimeConfig:
    """Inputs needed to resolve a within-scan acquisition schedule.

    ``settling_us`` uses physical microseconds rather than a driver-specific
    factor. It means ``STREAM_SETTLING_US`` for T4/T7, U6 stream settling
    factor times 10 us, and UE9 extra-settling factor times 5 us.

    For U3, ``resolution_index=None`` requests the UD driver's automatic
    choice, 0-3 are low-level indices, and 100-103 are explicit UD indices.
    For the other families, index 0 has its documented stream-mode meaning.

    Explicit ``channel_offsets_s`` have highest priority.  They are offsets
    from scan start (or any caller-chosen scan reference) for every position in
    the scan list.  A scalar ``interchannel_delay_s`` is the next-priority
    override and assumes equally spaced sequential samples.
    """

    device_type: LabJackDeviceTypeEnum
    actual_scan_rate_hz: float
    num_addresses: int
    resolution_index: int | None = 0
    input_range_v: float | None = 10.0
    settling_us: float = 0.0
    interchannel_delay_s: float | None = None
    channel_offsets_s: Sequence[float] | None = None


@dataclass(frozen=True, slots=True)
class ResolvedAcquisitionSchedule:
    """A validated, immutable acquisition schedule for one stream."""

    device_type: LabJackDeviceTypeEnum
    actual_scan_rate_hz: float
    aggregate_sample_rate_hz: float
    num_addresses: int
    resolution_index: int | None
    input_range_v: float | None
    configured_settling_us: float
    channel_offsets_s: tuple[float, ...]
    interchannel_delay_s: float | None
    basis: str
    values_are_typical: bool


@dataclass(frozen=True, slots=True)
class StreamSampleTimes:
    """Element-aligned indices and reconstructed acquisition times."""

    sample_times_s: np.ndarray
    element_indices: np.ndarray
    scan_indices: np.ndarray
    scan_positions: np.ndarray
    acquisition_schedule: ResolvedAcquisitionSchedule


_T4_DELAYS_US = {
    2: 47.0,
    3: 121.0,
    4: 230.0,
    5: 446.0,
}

_T7_DELAYS_US = {
    10.0: {
        2: 25.0,
        3: 45.0,
        4: 90.0,
        5: 170.0,
        6: 335.0,
        7: 670.0,
        8: 1335.0,
    },
    1.0: {
        1: 210.0,
        2: 220.0,
        3: 545.0,
        4: 585.0,
        5: 1200.0,
        6: 2415.0,
        7: 2750.0,
        8: 3415.0,
    },
    0.1: {
        1: 1040.0,
        2: 2105.0,
    },
}

_U3_DELAYS_US = {0: 320.0, 1: 82.0, 2: 42.0, 3: 12.5}
_U3_MAX_SAMPLE_RATES_HZ = {
    0: 2500.0,
    1: 10000.0,
    2: 20000.0,
    3: 50000.0,
}

_U6_DELAYS_US = {
    10.0: {
        1: 15.0,
        2: 30.0,
        3: 40.0,
        4: 110.0,
        5: 220.0,
        6: 440.0,
        7: 875.0,
        8: 1740.0,
    },
    1.0: {
        1: 205.0,
        2: 220.0,
        3: 545.0,
        4: 600.0,
        5: 1210.0,
        6: 2430.0,
        7: 2880.0,
        8: 3740.0,
    },
    0.1: {
        1: 1010.0,
        2: 2030.0,
        3: 2560.0,
        4: 2630.0,
        5: 2730.0,
        6: 2940.0,
        7: 3380.0,
        8: 4240.0,
    },
    0.01: {
        1: 2500.0,
        2: 2535.0,
        3: 2560.0,
        4: 2630.0,
        5: 2730.0,
        6: 2940.0,
        7: 3380.0,
        8: 4240.0,
    },
}

_UE9_DELAYS_US = {
    12: 12.0,
    13: 44.0,
    14: 158.0,
    15: 670.0,
    16: 2700.0,
}


def _normalise_range(
    value: float | None,
    supported: Sequence[float],
    device_type: LabJackDeviceTypeEnum,
) -> float:
    if value is None:
        raise StreamSampleTimeError(
            f"input_range_v is required for the {device_type.name} acquisition schedule."
        )
    candidate = float(value)
    for supported_value in supported:
        if isclose(candidate, supported_value, rel_tol=0.0, abs_tol=1e-12):
            return supported_value
    choices = ", ".join(str(item) for item in supported)
    raise StreamSampleTimeError(
        f"{device_type.name} input_range_v={candidate!r} has no published acquisition schedule; "
        f"supported half-ranges are {choices} V. Supply explicit offsets for other configurations."
    )


def _normalise_resolution(
    index: int | None,
    *,
    default: int,
    minimum: int,
    maximum: int,
    device_type: LabJackDeviceTypeEnum,
) -> int:
    resolved = default if index == 0 else index
    if (
        resolved is None
        or isinstance(resolved, bool)
        or not isinstance(resolved, (int, np.integer))
    ):
        raise StreamSampleTimeError(
            f"resolution_index must be an integer for {device_type.name}."
        )
    resolved = int(resolved)
    if not minimum <= resolved <= maximum:
        raise StreamSampleTimeError(
            f"resolution_index={resolved} is outside the documented "
            f"{device_type.name} stream range "
            f"{minimum}-{maximum}."
        )
    return resolved


def _validate_offsets(
    offsets: Sequence[float],
    scan_rate_hz: float,
    num_addresses: int,
) -> tuple[float, ...]:
    if len(offsets) != num_addresses:
        raise StreamSampleTimeError(
            f"Expected {num_addresses} channel offsets, received {len(offsets)}."
        )
    values = tuple(float(value) for value in offsets)
    if not values or not all(np.isfinite(values)):
        raise StreamSampleTimeError("Channel offsets must contain finite values.")
    if values[0] < 0.0 or any(right < left for left, right in zip(values, values[1:])):
        raise StreamSampleTimeError("Channel offsets must be non-negative and non-decreasing.")
    scan_period_s = 1.0 / scan_rate_hz
    if values[-1] >= scan_period_s:
        raise StreamSampleTimeError(
            f"Last channel offset {values[-1]:.12g} s does not fit inside the "
            f"{scan_period_s:.12g} s scan period."
        )
    return values


def _uniform_offsets(num_addresses: int, delay_s: float) -> tuple[float, ...]:
    return tuple(position * delay_s for position in range(num_addresses))


def _resolve_u3_resolution(index: int | None, aggregate_rate_hz: float) -> int:
    if index is None:
        for resolved, maximum_rate in _U3_MAX_SAMPLE_RATES_HZ.items():
            if aggregate_rate_hz <= maximum_rate:
                return resolved
        raise StreamSampleTimeError(
            "U3 aggregate sample rate exceeds the documented 50 ksample/s maximum."
        )

    if isinstance(index, bool) or not isinstance(index, (int, np.integer)):
        raise StreamSampleTimeError(
            "U3 resolution_index must be None, 0-3, or 100-103."
        )
    resolved = int(index)
    if 100 <= resolved <= 103:
        resolved -= 100
    if resolved not in _U3_DELAYS_US:
        raise StreamSampleTimeError(
            "U3 resolution_index must be None, low-level 0-3, or UD 100-103."
        )
    if aggregate_rate_hz > _U3_MAX_SAMPLE_RATES_HZ[resolved]:
        raise StreamSampleTimeError(
            f"U3 resolution {resolved} supports at most "
            f"{_U3_MAX_SAMPLE_RATES_HZ[resolved]:g} samples/s, "
            f"not {aggregate_rate_hz:g}."
        )
    return resolved


def resolve_acquisition_schedule(
    config: StreamSampleTimeConfig,
) -> ResolvedAcquisitionSchedule:
    """Resolve device/configuration dependencies into scan-position offsets.

    Datasheet-derived profiles are typical values.  Explicit overrides are
    treated as caller-supplied values and are not modified by settling rules.
    """

    device_type = config.device_type
    if not isinstance(device_type, LabJackDeviceTypeEnum):
        raise StreamSampleTimeError(
            "device_type must be a LabJackDeviceTypeEnum value."
        )
    if device_type not in (
        LabJackDeviceTypeEnum.U12,
        LabJackDeviceTypeEnum.U3,
        LabJackDeviceTypeEnum.T4,
        LabJackDeviceTypeEnum.U6,
        LabJackDeviceTypeEnum.T7,
        LabJackDeviceTypeEnum.T8,
        LabJackDeviceTypeEnum.UE9,
    ):
        raise StreamSampleTimeError(
            f"Sample-time reconstruction is not supported for {device_type.name}."
        )
    scan_rate_hz = float(config.actual_scan_rate_hz)
    if not np.isfinite(scan_rate_hz) or scan_rate_hz <= 0.0:
        raise StreamSampleTimeError(
            "actual_scan_rate_hz must be finite and greater than zero."
        )
    if isinstance(config.num_addresses, bool) or not isinstance(
        config.num_addresses, (int, np.integer)
    ):
        raise StreamSampleTimeError("num_addresses must be a positive integer.")
    num_addresses = int(config.num_addresses)
    if num_addresses <= 0:
        raise StreamSampleTimeError("num_addresses must be a positive integer.")
    settling_us = float(config.settling_us)
    if not np.isfinite(settling_us) or settling_us < 0.0:
        raise StreamSampleTimeError("settling_us must be finite and non-negative.")
    aggregate_rate_hz = scan_rate_hz * num_addresses

    if config.channel_offsets_s is not None:
        offsets = _validate_offsets(config.channel_offsets_s, scan_rate_hz, num_addresses)
        adjacent = np.diff(offsets)
        uniform_delay = (
            float(adjacent[0])
            if len(adjacent) and np.allclose(adjacent, adjacent[0])
            else None
        )
        return ResolvedAcquisitionSchedule(
            device_type, scan_rate_hz, aggregate_rate_hz, num_addresses,
            config.resolution_index, config.input_range_v, settling_us,
            offsets, uniform_delay, "explicit channel offsets", False,
        )

    if config.interchannel_delay_s is not None:
        delay_s = float(config.interchannel_delay_s)
        if not np.isfinite(delay_s) or delay_s < 0.0:
            raise StreamSampleTimeError(
                "interchannel_delay_s must be finite and non-negative."
            )
        offsets = _validate_offsets(
            _uniform_offsets(num_addresses, delay_s),
            scan_rate_hz,
            num_addresses,
        )
        return ResolvedAcquisitionSchedule(
            device_type, scan_rate_hz, aggregate_rate_hz, num_addresses,
            config.resolution_index, config.input_range_v, settling_us,
            offsets, delay_s, "explicit interchannel delay", False,
        )

    if num_addresses == 1:
        return ResolvedAcquisitionSchedule(
            device_type, scan_rate_hz, aggregate_rate_hz, num_addresses,
            config.resolution_index, config.input_range_v, settling_us,
            (0.0,), None, "single scan-list element", False,
        )

    delay_us: float | None = None
    resolution: int | None = config.resolution_index
    input_range_v = config.input_range_v
    basis = "datasheet auto-settling interchannel delay"

    if device_type is LabJackDeviceTypeEnum.T4:
        if settling_us != 0.0:
            raise StreamSampleTimeError(
                "The T4 datasheet does not provide a complete "
                "manual-settling-to-interchannel-delay "
                "formula. Supply interchannel_delay_s or channel_offsets_s."
            )
        resolution = _normalise_resolution(
            resolution,
            default=1,
            minimum=1,
            maximum=5,
            device_type=device_type,
        )
        if resolution == 1:
            delay_us = 40.0 if aggregate_rate_hz <= 20_000.0 else 13.0
        else:
            delay_us = _T4_DELAYS_US[resolution]

    elif device_type is LabJackDeviceTypeEnum.T7:
        if settling_us != 0.0:
            raise StreamSampleTimeError(
                "The T7 datasheet does not provide a complete "
                "manual-settling-to-interchannel-delay "
                "formula. Supply interchannel_delay_s or channel_offsets_s."
            )
        resolution = _normalise_resolution(
            resolution,
            default=1,
            minimum=1,
            maximum=8,
            device_type=device_type,
        )
        input_range_v = _normalise_range(
            input_range_v,
            (10.0, 1.0, 0.1, 0.01),
            device_type,
        )
        if input_range_v == 10.0 and resolution == 1:
            delay_us = 15.0 if aggregate_rate_hz <= 60_000.0 else 8.0
        else:
            try:
                delay_us = _T7_DELAYS_US[input_range_v][resolution]
            except KeyError as error:
                raise StreamSampleTimeError(
                    f"T7 ±{input_range_v:g} V, resolution {resolution} is not supported for a "
                    "multi-address stream in the published timing table."
                ) from error

    elif device_type is LabJackDeviceTypeEnum.T8:
        resolution = _normalise_resolution(
            resolution,
            default=1,
            minimum=1,
            maximum=16,
            device_type=device_type,
        )
        offsets = _validate_offsets((0.0,) * num_addresses, scan_rate_hz, num_addresses)
        return ResolvedAcquisitionSchedule(
            device_type, scan_rate_hz, aggregate_rate_hz, num_addresses,
            resolution, input_range_v, settling_us, offsets, 0.0,
            "simultaneous T8 analog-input capture", False,
        )

    elif device_type is LabJackDeviceTypeEnum.U3:
        if settling_us != 0.0:
            raise StreamSampleTimeError(
                "The U3 StreamConfig table has no stream settling-time term. "
                "Supply an explicit sample-time override if needed."
            )
        resolution = _resolve_u3_resolution(resolution, aggregate_rate_hz)
        delay_us = _U3_DELAYS_US[resolution]
        basis = "U3 datasheet resolution-dependent interchannel delay"

    elif device_type is LabJackDeviceTypeEnum.U6:
        if settling_us != 0.0:
            raise StreamSampleTimeError(
                "The U6 table gives complete interchannel delays only for "
                "auto settling. Supply interchannel_delay_s or "
                "channel_offsets_s for a nonzero settling factor."
            )
        resolution = _normalise_resolution(
            resolution,
            default=1,
            minimum=1,
            maximum=8,
            device_type=device_type,
        )
        input_range_v = _normalise_range(
            input_range_v, (10.0, 1.0, 0.1, 0.01), device_type
        )
        delay_us = _U6_DELAYS_US[input_range_v][resolution]
        basis = "U6 Table 3.2.2 auto-settling interchannel delay"

    elif device_type is LabJackDeviceTypeEnum.UE9:
        if resolution is None:
            raise StreamSampleTimeError(
                "UE9 resolution_index must be in the stream range 0-16."
            )
        if isinstance(resolution, bool) or not isinstance(
            resolution, (int, np.integer)
        ):
            raise StreamSampleTimeError(
                "UE9 resolution_index must be an integer from 0 through 16."
            )
        resolution = int(resolution)
        resolution = 12 if 0 <= resolution <= 12 else resolution
        if resolution not in _UE9_DELAYS_US:
            raise StreamSampleTimeError(
                "UE9 stream resolution must resolve to 12, 13, 14, 15, or 16 bits."
            )
        delay_us = _UE9_DELAYS_US[resolution] + settling_us
        basis = "UE9 Appendix A delay plus Section 2.7 extra settling"

    elif device_type is LabJackDeviceTypeEnum.U12:
        if settling_us != 0.0:
            raise StreamSampleTimeError(
                "The U12 acquisition schedule has no settling_us parameter."
            )
        delay_s = 1.0 / aggregate_rate_hz
        offsets = _validate_offsets(
            _uniform_offsets(num_addresses, delay_s),
            scan_rate_hz,
            num_addresses,
        )
        return ResolvedAcquisitionSchedule(
            device_type,
            scan_rate_hz,
            aggregate_rate_hz,
            num_addresses,
            resolution,
            input_range_v,
            settling_us,
            offsets,
            delay_s,
            "U12 evenly spaced stream samples",
            False,
        )

    if delay_us is None:
        raise AssertionError("Acquisition schedule did not produce an interchannel delay.")
    delay_s = delay_us * 1e-6
    offsets = _validate_offsets(
        _uniform_offsets(num_addresses, delay_s), scan_rate_hz, num_addresses
    )
    return ResolvedAcquisitionSchedule(
        device_type, scan_rate_hz, aggregate_rate_hz, num_addresses,
        resolution, input_range_v, settling_us, offsets, delay_s, basis, True,
    )


def reconstruct_stream_sample_times(
    raw_data: Sequence[object] | np.ndarray,
    schedule: StreamSampleTimeConfig | ResolvedAcquisitionSchedule,
    *,
    start_element_index: int = 0,
    time_origin_s: float = 0.0,
    scan_start_times_s: Sequence[float] | np.ndarray | None = None,
) -> StreamSampleTimes:
    """Reconstruct one acquisition time for every flat stream element.

    ``time_origin_s`` is the time assigned to scan 0's reference point.  For
    datasheet profiles, position 0 has offset zero, so this is the acquisition
    time of the first element rather than the undocumented scan-start-to-first-
    sample delay.

    ``start_element_index`` preserves phase when processing packet/chunk
    boundaries that do not align with a complete scan.  ``scan_start_times_s``
    can replace the regular scan-rate grid for externally clocked streams.
    Dummy values such as -9999 remain ordinary timeline positions.
    """

    values = np.asarray(raw_data)
    if values.ndim != 1:
        raise StreamSampleTimeError("raw_data must be a flat, one-dimensional stream array.")
    if isinstance(start_element_index, bool) or not isinstance(
        start_element_index, (int, np.integer)
    ):
        raise StreamSampleTimeError("start_element_index must be a non-negative integer.")
    start_element_index = int(start_element_index)
    if start_element_index < 0:
        raise StreamSampleTimeError("start_element_index must be a non-negative integer.")
    time_origin_s = float(time_origin_s)
    if not np.isfinite(time_origin_s):
        raise StreamSampleTimeError("time_origin_s must be finite.")

    resolved = (
        schedule
        if isinstance(schedule, ResolvedAcquisitionSchedule)
        else resolve_acquisition_schedule(schedule)
    )
    element_indices = np.arange(
        start_element_index,
        start_element_index + values.size,
        dtype=np.int64,
    )
    scan_indices, scan_positions = np.divmod(element_indices, resolved.num_addresses)
    offsets = np.asarray(resolved.channel_offsets_s, dtype=np.float64)

    if scan_start_times_s is None:
        scan_times = scan_indices.astype(np.float64) / resolved.actual_scan_rate_hz
    else:
        starts = np.asarray(scan_start_times_s, dtype=np.float64)
        if starts.ndim != 1 or not np.all(np.isfinite(starts)):
            raise StreamSampleTimeError(
                "scan_start_times_s must be a finite one-dimensional array."
            )
        if scan_indices.size and int(scan_indices[-1]) >= starts.size:
            raise StreamSampleTimeError(
                "scan_start_times_s does not cover all referenced scan indices."
            )
        scan_times = starts[scan_indices]

    sample_times_s = time_origin_s + scan_times + offsets[scan_positions]
    for array in (sample_times_s, element_indices, scan_indices, scan_positions):
        array.setflags(write=False)
    return StreamSampleTimes(
        sample_times_s=sample_times_s,
        element_indices=element_indices,
        scan_indices=scan_indices,
        scan_positions=scan_positions,
        acquisition_schedule=resolved,
    )
