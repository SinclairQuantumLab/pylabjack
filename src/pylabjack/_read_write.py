"""Execute ordered, on-demand numeric register reads and writes.

One :class:`ReadWrite` object owns the complete command-response request,
effective ``ljm.eNames`` frames, aligned results, host-observed timing, device
identity, and software provenance.  Public ``LabJackDevice.read()``,
``write()``, and ``read_write()`` calls all normalize into this one backend.

This module intentionally supports one numeric value per named register. LJM
array, string, byte-array, and address/type variants are separate register-
shape features; they are not time-spaced sampling and are not silently folded
into this scalar contract.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
import math
from numbers import Real
from time import perf_counter_ns
from typing import Any, Literal

from labjack import ljm

from ._ljm_aux import LabJackReadWriteError
from ._software_provenance import SoftwareProvenance
from .labjack_device import LabJackDevice, LabJackDeviceIdentity


ReadWriteAction = Literal["read", "write"]
ReadWriteMethod = Literal["read", "write", "read_write"]


@dataclass(frozen=True, slots=True)
class ReadWriteCommand:
    """One normalized scalar register command before execution."""

    action: ReadWriteAction
    name: str
    value: float | None = None


@dataclass(frozen=True, slots=True)
class ReadWriteResult:
    """One result aligned with a normalized command."""

    action: ReadWriteAction
    name: str
    requested_value: float | None
    value: float


def _validate_register_name(name: Any) -> str:
    if not isinstance(name, str):
        raise TypeError("Register names must be strings.")
    if not name or name != name.strip():
        raise ValueError(
            "Register names must be non-empty and have no surrounding whitespace."
        )
    if not name.isascii():
        raise ValueError("Register names must contain ASCII characters only.")
    if any(character.isspace() or ord(character) < 32 for character in name):
        raise ValueError(
            "Register names must not contain whitespace or control characters."
        )
    return name


def _validate_write_value(value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise TypeError("Register write values must be real numbers, not booleans.")
    try:
        numeric_value = float(value)
    except (OverflowError, ValueError) as error:
        raise ValueError(
            "Register write values must fit in a finite floating-point value."
        ) from error
    if not math.isfinite(numeric_value):
        raise ValueError("Register write values must be finite real numbers.")
    return numeric_value


def _is_nonstring_sequence(value: Any) -> bool:
    return isinstance(value, Sequence) and not isinstance(
        value,
        (str, bytes, bytearray),
    )


def _normalize_read_request(
    names: str | Sequence[str],
) -> tuple[ReadWriteCommand, ...]:
    if isinstance(names, str):
        normalized_names = (names,)
    elif _is_nonstring_sequence(names):
        normalized_names = tuple(names)
    else:
        raise TypeError("read() requires one register name or a sequence of names.")

    if not normalized_names:
        raise ValueError("read() requires at least one register name.")
    return tuple(
        ReadWriteCommand("read", _validate_register_name(name))
        for name in normalized_names
    )


def _normalize_write_request(
    name_or_entries: str | Sequence[Sequence[Any]],
    value: Real | None,
) -> tuple[ReadWriteCommand, ...]:
    if isinstance(name_or_entries, str):
        if value is None:
            raise ValueError(
                "write() requires a value when one register name is given."
            )
        return (
            ReadWriteCommand(
                "write",
                _validate_register_name(name_or_entries),
                _validate_write_value(value),
            ),
        )

    if value is not None:
        raise ValueError(
            "write() value must be omitted when an ordered sequence of "
            "(name, value) pairs is given."
        )
    if not _is_nonstring_sequence(name_or_entries):
        raise TypeError(
            "write() requires one name plus one value or an ordered sequence "
            "of (name, value) pairs."
        )

    entries = tuple(name_or_entries)
    if not entries:
        raise ValueError("write() requires at least one (name, value) pair.")

    normalized = []
    for entry in entries:
        if not _is_nonstring_sequence(entry) or len(entry) != 2:
            raise TypeError("Each write entry must be a (name, value) pair.")
        name, entry_value = entry
        normalized.append(
            ReadWriteCommand(
                "write",
                _validate_register_name(name),
                _validate_write_value(entry_value),
            )
        )
    return tuple(normalized)


def _normalize_mapping_command(command: Mapping[str, Any]) -> ReadWriteCommand:
    allowed_keys = {"action", "name", "value"}
    extra_keys = set(command) - allowed_keys
    if extra_keys:
        extras = ", ".join(sorted(map(str, extra_keys)))
        raise ValueError(f"Unknown read_write() command keys: {extras}.")
    if "action" not in command or "name" not in command:
        raise ValueError(
            "Each read_write() command requires 'action' and 'name'."
        )

    action = command["action"]
    name = _validate_register_name(command["name"])
    if action == "read":
        if "value" in command:
            raise ValueError("A read command must not include 'value'.")
        return ReadWriteCommand("read", name)
    if action == "write":
        if "value" not in command:
            raise ValueError("A write command requires 'value'.")
        return ReadWriteCommand(
            "write",
            name,
            _validate_write_value(command["value"]),
        )
    raise ValueError("Command action must be exactly 'read' or 'write'.")


def _normalize_sequence_command(command: Sequence[Any]) -> ReadWriteCommand:
    if not command:
        raise ValueError("A read_write() command must not be empty.")

    action = command[0]
    if action == "read" and len(command) == 2:
        return ReadWriteCommand(
            "read",
            _validate_register_name(command[1]),
        )
    if action == "write" and len(command) == 3:
        return ReadWriteCommand(
            "write",
            _validate_register_name(command[1]),
            _validate_write_value(command[2]),
        )
    raise ValueError(
        "Tuple/list commands must be ('read', name) or "
        "('write', name, value)."
    )


def _normalize_read_write_request(
    commands: Sequence[Mapping[str, Any] | Sequence[Any]],
) -> tuple[ReadWriteCommand, ...]:
    if not _is_nonstring_sequence(commands):
        raise TypeError("read_write() requires an ordered sequence of commands.")

    requested_commands = tuple(commands)
    if not requested_commands:
        raise ValueError("read_write() requires at least one command.")

    normalized = []
    for command in requested_commands:
        if isinstance(command, Mapping):
            normalized.append(_normalize_mapping_command(command))
        elif _is_nonstring_sequence(command):
            normalized.append(_normalize_sequence_command(command))
        else:
            raise TypeError(
                "Each read_write() command must be a mapping or tuple/list."
            )
    return tuple(normalized)


class ReadWrite:
    """One completed ordered ``ljm.eNames`` command-response operation."""

    @property
    def method(self) -> ReadWriteMethod:
        return self._method

    @property
    def requested_input(self):
        return deepcopy(self._requested_input)

    @property
    def commands(self) -> tuple[ReadWriteCommand, ...]:
        return self._commands

    @property
    def results(self) -> tuple[ReadWriteResult, ...]:
        return self._results

    @property
    def values(self) -> tuple[float, ...]:
        return tuple(
            result.value
            for result in self._results
            if result.action == "read"
        )

    @property
    def value(self) -> float:
        values = self.values
        if len(values) != 1:
            raise ValueError(
                "value is available only when exactly one register was read."
            )
        return values[0]

    @property
    def written_values(self) -> tuple[float, ...]:
        return tuple(
            command.value
            for command in self._commands
            if command.action == "write" and command.value is not None
        )

    @property
    def num_frames(self) -> int:
        return len(self._commands)

    @property
    def num_reads(self) -> int:
        return sum(command.action == "read" for command in self._commands)

    @property
    def num_writes(self) -> int:
        return sum(command.action == "write" for command in self._commands)

    @property
    def ljm_names(self) -> tuple[str, ...]:
        return self._ljm_names

    @property
    def ljm_directions(self) -> tuple[int, ...]:
        return self._ljm_directions

    @property
    def ljm_num_values(self) -> tuple[int, ...]:
        return self._ljm_num_values

    @property
    def ljm_values_before(self) -> tuple[float, ...]:
        return self._ljm_values_before

    @property
    def ljm_values_after(self) -> tuple[float, ...]:
        return self._ljm_values_after

    @property
    def started_at_utc(self) -> datetime:
        return self._started_at_utc

    @property
    def finished_at_utc(self) -> datetime:
        return self._finished_at_utc

    @property
    def execution_duration_s(self) -> float:
        return self._execution_duration_s

    @property
    def device_identity(self) -> LabJackDeviceIdentity:
        return self._device_identity

    @property
    def software_provenance(self) -> SoftwareProvenance:
        return self._software_provenance

    def __init__(
        self,
        device: LabJackDevice,
        *,
        _method: ReadWriteMethod,
        _requested_input: Any,
        _commands: tuple[ReadWriteCommand, ...],
    ) -> None:
        self._device = device
        self._method = _method
        self._requested_input = deepcopy(_requested_input)
        self._commands = _commands
        self._device_identity = device.device_identity
        self._software_provenance = device.software_provenance
        self._handle = device._handle

        self._ljm_names = tuple(command.name for command in _commands)
        self._ljm_directions = tuple(
            ljm.constants.READ
            if command.action == "read"
            else ljm.constants.WRITE
            for command in _commands
        )
        self._ljm_num_values = (1,) * len(_commands)
        self._ljm_values_before = tuple(
            0.0 if command.action == "read" else float(command.value)
            for command in _commands
        )

        self._started_at_utc = datetime.now(timezone.utc)
        started_ns = perf_counter_ns()
        try:
            returned_values = ljm.eNames(
                self._handle,
                len(_commands),
                list(self._ljm_names),
                list(self._ljm_directions),
                list(self._ljm_num_values),
                list(self._ljm_values_before),
            )
            if len(returned_values) != len(_commands):
                raise LabJackReadWriteError(
                    "LJM returned a value array that does not match the "
                    "command count."
                )
            self._ljm_values_after = tuple(
                float(value) for value in returned_values
            )
        except ljm.LJMError as error:
            raise LabJackReadWriteError(
                "LabJack library-level error during read/write."
            ) from error
        except LabJackReadWriteError:
            raise
        except Exception as error:
            raise LabJackReadWriteError(
                "Non LabJack library-level error during read/write."
            ) from error
        finally:
            finished_ns = perf_counter_ns()
            self._finished_at_utc = datetime.now(timezone.utc)
            self._execution_duration_s = (finished_ns - started_ns) / 1e9

        self._results = tuple(
            ReadWriteResult(
                action=command.action,
                name=command.name,
                requested_value=command.value,
                value=result_value,
            )
            for command, result_value in zip(
                self._commands,
                self._ljm_values_after,
                strict=True,
            )
        )

    def __str__(self) -> str:
        values = self.values
        if len(values) <= 8:
            value_summary = repr(values)
        else:
            value_summary = f"{values[:8]!r} ... ({len(values)} reads total)"
        return (
            "LabJack read/write operation:"
            f"\n\tMethod: {self.method}"
            f"\n\tFrames: {self.num_frames} "
            f"({self.num_reads} read, {self.num_writes} write)"
            f"\n\tHost-observed execution time: "
            f"{self.execution_duration_s:.6f} s"
            f"\n\tRead values: {value_summary}"
        )
