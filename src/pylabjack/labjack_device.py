from labjack import ljm
from ._ljm_aux import (
    LabJackConnectionError,
    LabJackConnectionTypeEnum,
    LabJackDeviceTypeEnum,
    LabJackDisconnectionError,
    LabJackLibraryConfigurationError,
    LabJackNoConnectionError,
    LabJackRegisterConfigurationError,
    LabJackTriggerEdgeEnum,
    LabJackTriggerModeEnum,
)
from ._software_provenance import (
    SoftwareProvenance,
    get_software_provenance,
)
from datetime import datetime
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from numbers import Real
import sys
from typing import Any, TYPE_CHECKING
if TYPE_CHECKING:
    from ._read_write import ReadWrite
    from ._stream import Stream


def _format_tagged_message(tag: str, message: str) -> str:
    """Format a tagged operational message with aligned continuation lines."""
    tag_text = str(tag).strip().removesuffix(":")
    if not tag_text or "\n" in tag_text or "\r" in tag_text:
        raise ValueError("tag must be a non-empty, single-line value.")

    prefix = f"{tag_text}: "
    lines = str(message).splitlines() or [""]
    continuation_indent = " " * len(prefix)
    return prefix + f"\n{continuation_indent}".join(lines)


def _print_tagged_message(tag: str, message: str, *, flush: bool = False) -> None:
    """Print a tagged operational message using the shared block format."""
    print(_format_tagged_message(tag, message), flush=flush)


@dataclass(frozen=True, slots=True)
class LabJackDeviceIdentity:
    """Immutable actual-device identity shared with operation objects."""

    device_type: LabJackDeviceTypeEnum
    connection_type: LabJackConnectionTypeEnum
    serial_number: int | None
    ip_address: str | None
    port: int | None


class LabJackDevice:
    """A LabJack connection that can be reused across device operations.

    Example usage:
    - Keep one connection open for multiple on-demand operations, then close it
      explicitly:

        device = LabJackDevice(
            device_type=LabJackDeviceTypeEnum["<DEVICE_TYPE>"],
            connection_type=LabJackConnectionTypeEnum["<CONNECTION_TYPE>"],
            device_identifier="<DEVICE_IDENTIFIER>",
        )
        try:
            device.stream(...)
            device.stream(...)
        finally:
            device.close()

    - Use a context manager for a bounded connection lifetime:

        with LabJackDevice(
            device_type=LabJackDeviceTypeEnum["<DEVICE_TYPE>"],
            connection_type=LabJackConnectionTypeEnum["<CONNECTION_TYPE>"],
            device_identifier="<DEVICE_IDENTIFIER>",
        ) as device:
            stream_data = device.stream(...)
            # process stream_data ...
    """

    # >>>>> class setting >>>>>

    # Read-only properties
    @property
    def device_type(self): return self._device_type
    @property
    def connection_type(self): return self._connection_type
    @property
    def device_identifier(self): return self._device_identifier
    @property
    def serial_number(self): return self._serial_number
    @property
    def IP_address(self): return self._IP_address
    @property
    def port(self): return self._port
    @property
    def max_bytes_per_MB(self): return self._max_bytes_per_MB
    @property
    def software_provenance(self) -> SoftwareProvenance:
        return self._software_provenance
    @property
    def device_identity(self) -> LabJackDeviceIdentity:
        return self._device_identity

    def __init__(
            self,
            device_type: LabJackDeviceTypeEnum,
            connection_type: LabJackConnectionTypeEnum,
            device_identifier: str
        ) -> None:
        """
        Initialize the LabJackDevice.

        Parameters:
            device_type: An enum value indicating the LabJack device type (e.g., LabJackDeviceTypeEnum.T7).
            connection_type: An enum value indicating the connection type (e.g., LabJackConnectionTypeEnum.ETHERNET).
            device_identifier: The device identifier (e.g., IP address or serial number).
        """
        # Connection configuration
        self._device_type = device_type
        self._connection_type = connection_type
        self._device_identifier = device_identifier
        self._handle = None
        self._serial_number = None
        self._IP_address = None
        self._port = None
        self._max_bytes_per_MB = None
        self._device_identity = None
        self._software_provenance = get_software_provenance(
            package_name="pylabjack",
            source_path=__file__,
        )

        self._connect()
        print()
        print(self)
        print()

    def __enter__(self) -> "LabJackDevice":
        """Return this already-connected device for a bounded lifetime."""
        self._check_connection()
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> bool:
        """Close on context exit without hiding an operation failure."""
        try:
            self.close()
        except BaseException as close_error:
            if exc_value is None:
                raise
            exc_value.add_note(
                f"LabJack close also failed: {close_error!r}"
            )
        return False

    def __del__(self) -> None:
        """Best-effort fallback; normal cleanup uses ``close`` or ``with``."""
        try:
            self.close()
        except BaseException:
            # Destructors cannot provide deterministic error reporting.
            pass

    def __str__(self) -> str:
        msg = "LabJack device instance:"
        msg += f"\n\tDevice type: {self._device_type.name}"
        msg += f"\n\tConnection type: {self._connection_type.name}"
        msg += f"\n\tIP address: {self._IP_address}, Port: {self._port}"
        msg += f"\n\tSerial number: {self._serial_number}"
        msg += f"\n\tMax bytes per MB: {self._max_bytes_per_MB}"
        return msg

    # <<<<< class setting <<<<<



    # >>>>> LabJack connection >>>>>

    def _connect(self) -> None:
        """Open one handle and load device info transactionally."""
        if self._handle is not None:
            raise LabJackConnectionError(
                "This LabJackDevice already owns an open connection handle."
            )

        print(">>> Connecting to LabJack... ", end="")

        # Open device (using names of enums)
        try:
            start = datetime.now()
            handle = ljm.openS(
                self._device_type.name,
                self._connection_type.name,
                self._device_identifier,
            )
            end = datetime.now()
        except ljm.LJMError as ljmex:
            raise LabJackConnectionError("LabJack library-level error") from ljmex
        except Exception as ex:
            raise LabJackConnectionError("Non LabJack library-level error") from ex

        td_exe = end - start

        # Get device info and store it
        # https://support.labjack.com/docs/gethandleinfo-ljm-user-s-guide
        try:
            info = ljm.getHandleInfo(handle)
            IP_address = ljm.numberToIP(info[3])
        except BaseException as original_error:
            # The context manager has not been entered yet, so roll back a
            # partially initialized connection here.
            try:
                ljm.close(handle)
            except BaseException as close_error:
                original_error.add_note(
                    "Closing the partially initialized LabJack handle also "
                    f"failed: {close_error!r}"
                )

            if isinstance(original_error, ljm.LJMError):
                raise LabJackConnectionError(
                    "LabJack library-level error while loading device info"
                ) from original_error
            if isinstance(original_error, Exception):
                raise LabJackConnectionError(
                    "Non LabJack library-level error while loading device info"
                ) from original_error
            raise

        # Publish the handle only after every initialization step succeeds.
        self._handle = handle
        self._serial_number = info[2]
        self._IP_address = IP_address
        self._port = info[4]
        self._max_bytes_per_MB = info[5]
        self._device_identity = LabJackDeviceIdentity(
            device_type=self._device_type,
            connection_type=self._connection_type,
            serial_number=self._serial_number,
            ip_address=self._IP_address,
            port=self._port,
        )

        print(f"Done. Execution time: {td_exe.total_seconds():.6f} s")

    def _check_connection(self) -> None:
        if self._handle is None:
            raise LabJackNoConnectionError("LabJack connection handle is not assigned.")

    def close(self) -> None:
        """Close this device's handle once; repeated calls are no-ops."""
        handle = self._handle
        if handle is None:
            return

        print(f">>> Disconnecting LabJack (SN: {self._serial_number})... ", end="")

        try:
            start = datetime.now()
            ljm.close(handle)
            end = datetime.now()
            td_exe = end - start
        except ljm.LJMError as ljmex:
            raise LabJackDisconnectionError("LabJack library-level error") from ljmex
        except Exception as ex:
            raise LabJackDisconnectionError("Non LabJack library-level error") from ex
        else:
            # Keep a failed-close handle assigned because closure was not
            # confirmed. A successful close makes future calls idempotent.
            self._handle = None

        print(f"Done. Execution time: {td_exe.total_seconds():.6f} s")

    def _disconnect(self) -> None:
        """Compatibility alias for the public, idempotent ``close`` method."""
        self.close()

    # <<<<< LabJack connection <<<<<



    # >>>>> LabJack configuration >>>>>

    def configure_library(self, **kwargs: int | float | str ) -> None:
        """
        Configure `ljm` library.

        Refer to https://support.labjack.com/docs/ljm-library-configuration-functions for the list of the configurations.

        Args: keyward arguments
        - key                           : configuration name
        - value (int or float or str)   : corresponding value to set

        cf. From the link: "Whenever LJM is started up, it is loaded with default values, so any desired configurations must be applied each time LJM is started."
            Refer to `./ljm_startup_configs.json` file and https://support.labjack.com/docs/ljm-startup-configs for the default configuration.

        ljm methods used:
        - https://support.labjack.com/docs/writelibraryconfigs-ljm-user-s-guide
        - https://support.labjack.com/docs/writelibraryconfigstrings-ljm-user-s-guide
        """
        # check connection
        self._check_connection()

        # check inputs
        handle = self._handle
        N_config = len(kwargs)
        if N_config < 1:
            raise ValueError("No given configuration.")

        for key, value in kwargs.items():
            if isinstance(value, (int, float, str)) is not True:
                raise ValueError(f"LabJack configuration value should be number or string\n\tInput configuration: {key} = {value}")

        try:
            for key, value in kwargs.items():
                if isinstance(value, str):
                    # configure string values
                    ljm.writeLibraryConfigStringS(key, value)
                else:
                    ljm.writeLibraryConfigS(key, value)
        except ljm.LJMError as ljmex:
            raise LabJackLibraryConfigurationError("LabJack library-level error") from ljmex
        except Exception as ex:
            raise LabJackLibraryConfigurationError("Non LabJack library-level error") from ex

    def configure_register(self, *,
                  AIN_ALL_NEGATIVE_CH=ljm.constants.GND,
                  AIN_ALL_RANGE=10.0,
                  **kwargs: int | float | str):
        """
        Configure LabJack device register
        Refer to the following links for the list of the configurations.
        - https://support.labjack.com/docs/t-series-datasheet
        - https://support.labjack.com/docs/3-1-modbus-map-t-series-datasheet
        - https://support.labjack.com/docs/3-1-2-printable-modbus-map

        Args: keyward arguments
        - key                           : configuration name
        - value (int or float or str)   : corresponding value to set

        Useful examples:
        - AIN<channel number or _ALL>_NEGATIVE_CH = ljm.constants.GND
          Set specified or all the analog channels to be single-ended (i.e., reading referenced to the ground)
          https://support.labjack.com/docs/14-0-analog-inputs-t-series-datasheet#id-14.0AnalogInputs[T-SeriesDatasheet]-Single-endedorDifferential-T7Only

          Examples:
            - AIN0_NEGATIVE_CH = ljm.constants.GND
            - AIN_ALL_NEGATIVE_CH = ljm.constants.GND

        - AIN<channel number or _ALL>_RANGE = <voltage in V>
          Set specified or all the channel to have +-<voltage in V> as the voltage range
          https://support.labjack.com/docs/14-0-analog-inputs-t-series-datasheet#id-14.0AnalogInputs[T-SeriesDatasheet]-Range/Gain-T7/T8
          e.g., AIN_ALL_NEGATIVE_CH = 10.0 (cf. LabJack default value)

        cf. Unlike `ljm` library configuration, the Modbus register values are not reset from power cycling or new connections
            Relevant references:
        - Factory & Power-up defaults configuration through Kippling app
            https://support.labjack.com/docs/general-configuration#GeneralConfiguration-Power-UpDefaults
        - I/O configuration through programing
            https://support.labjack.com/docs/24-0-io-config-_default-t-series-datasheet
        - Factory default values (search keyword: `power-up default`):
            https://support.labjack.com/docs/15-0-dac-t-series-datasheet#id-15.0DAC[T-SeriesDatasheet]-Power-upDefaults
            https://support.labjack.com/docs/14-0-analog-inputs-t-series-datasheet (default values scattered around...)
            https://support.labjack.com/docs/13-0-digital-i-o-t-series-datasheet#id-13.0DigitalI/O[T-SeriesDatasheet]-Power-upDefaults
            https://support.labjack.com/docs/configuring-reading-a-counter

        ljm methods used:
        - https://support.labjack.com/docs/general-configuration
        - https://support.labjack.com/docs/ewritenames-ljm-user-s-guide
        - https://support.labjack.com/docs/ewritenamestring-ljm-user-s-guide
        """
        # check connection
        self._check_connection()

        # add specified arguments in the configuration
        kwargs.update({
            "AIN_ALL_NEGATIVE_CH": AIN_ALL_NEGATIVE_CH,
            "AIN_ALL_RANGE": AIN_ALL_RANGE,
        })

        # check inputs
        handle = self._handle
        N_config = len(kwargs)
        if N_config < 1:
            raise ValueError("No given configuration.")

        for key, value in kwargs.items():
            if isinstance(value, (int, float, str)) is not True:
                raise ValueError(f"LabJack configuration value should be number or string\n\tInput configuration: {key} = {value}")

        try:
            keys_number = []; values_number = []
            for key, value in kwargs.items():
                if isinstance(value, str):
                    # configure string values
                    ljm.eWriteNameString(key, value)
                else:
                    keys_number.append(key); values_number.append(value)
            # configure number values
            N_config_number = len(keys_number)
            ljm.eWriteNames(handle, N_config_number, keys_number, values_number)
        except ljm.LJMError as ljmex:
            raise LabJackRegisterConfigurationError("LabJack library-level error") from ljmex
        except Exception as ex:
            raise LabJackRegisterConfigurationError("Non LabJack library-level error") from ex

    # <<<<< LabJack configuration <<<<<




    # >>>>>>> LabJack operation >>>>>>>
    # to be implemented in a separate protected file (i.e., in ./_XXX.py; class defined in the file does not need to be protected)

    # >>>>> command-response numeric register I/O >>>>>
    # implemented in ./_read_write.py

    def read_write(
        self,
        commands: Sequence[Mapping[str, Any] | Sequence[Any]],
    ) -> 'ReadWrite':
        """Run an explicitly ordered mixture of scalar reads and writes.

        Each command is either a mapping such as
        ``{"action": "read", "name": "AIN0"}`` or a compact sequence such
        as ``("write", "DAC0", 1.5)``. The original order and duplicate names
        are preserved in one ``ljm.eNames()`` call.
        """
        from ._read_write import ReadWrite, _normalize_read_write_request

        normalized = _normalize_read_write_request(commands)
        self._check_connection()
        return ReadWrite(
            self,
            _method="read_write",
            _requested_input=commands,
            _commands=normalized,
        )

    def read(self, names: str | Sequence[str]) -> 'ReadWrite':
        """Read one named scalar register or an ordered sequence of names."""
        from ._read_write import ReadWrite, _normalize_read_request

        normalized = _normalize_read_request(names)
        self._check_connection()
        return ReadWrite(
            self,
            _method="read",
            _requested_input=names,
            _commands=normalized,
        )

    def write(
        self,
        name_or_entries: str | Sequence[Sequence[Any]],
        value: Real | None = None,
    ) -> 'ReadWrite':
        """Write one name/value or an ordered sequence of name/value pairs."""
        from ._read_write import ReadWrite, _normalize_write_request

        normalized = _normalize_write_request(name_or_entries, value)
        requested_input = (
            (name_or_entries, value)
            if isinstance(name_or_entries, str)
            else name_or_entries
        )
        self._check_connection()
        return ReadWrite(
            self,
            _method="write",
            _requested_input=requested_input,
            _commands=normalized,
        )

    # <<<<< command-response numeric register I/O <<<<<

    # >>>>> stream >>>>>
    # implemented in ./_stream.py

    def stream(
            self,
            *,
            scan_rate_Hz: float,
            duration_s: float = 1,
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
        ) -> 'Stream':
        """Configure and run one unified LabJack stream session.

        Use either grouped ``inputs``/``outputs`` mappings or an ordered
        ``channels`` sequence with ``input_config``/``output_config``. Both
        forms normalize into the same internal scan plan. Stream-Out entries
        are represented by that plan but execution is not implemented yet.
        """
        from ._stream import Stream, _normalize_stream_plan

        plan = _normalize_stream_plan(
            scan_rate_Hz=scan_rate_Hz,
            duration_s=duration_s,
            inputs=inputs,
            outputs=outputs,
            channels=channels,
            input_config=input_config,
            output_config=output_config,
            do_trigger=do_trigger,
            trigger_channel=trigger_channel,
            trigger_mode=trigger_mode,
            trigger_edge=trigger_edge,
            trigger_timeout_s=trigger_timeout_s,
        )
        self._check_connection()
        return Stream(self, _plan=plan)

    # <<<<< stream <<<<<

    # <<<<<<< LabJack operation <<<<<<<

# example usage
if __name__ == "__main__":
    # Command template:
    # uv run python -m pylabjack.labjack_device <DEVICE_TYPE> <CONNECTION_TYPE> <DEVICE_IDENTIFIER>
    #
    # Values are used directly. Missing arguments, unknown enum member names,
    # and invalid LJM identifiers intentionally raise their native errors.
    device_type = LabJackDeviceTypeEnum[sys.argv[1]]
    connection_type = LabJackConnectionTypeEnum[sys.argv[2]]
    device_identifier = sys.argv[3]

    # connect to LabJack
    with LabJackDevice(
        device_type=device_type,
        connection_type=connection_type,
        device_identifier=device_identifier,
    ) as lj_device:
        # # (Optional) configure `ljm` library
        # # If not run, default configuration will be used. Refer to the docstring of LabJackDevice.configure_library() method.
        # lj_device.configure_library()

        # (Optional) configure LabJack device register
        # Better to run as the values will be the ones last used or power-up defaults.
        # Refer to the docstring LabJackDevice.configure_register() method.
        lj_device.configure_register(
            AIN_ALL_NEGATIVE_CH=ljm.constants.GND,
            AIN_ALL_RANGE=10,
        )
