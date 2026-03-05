"""
GPIO-based MAX31855 thermocouple sensor interface.

This module provides a clean interface for reading temperature data from
MAX31855 thermocouple amplifiers connected via SPI to GPIO pins.
"""

from importlib import import_module
from typing import Any, Literal


class SensorError(Exception):
    """Raised when a sensor communication error occurs."""


class MAX31855:
    """
    Interface for MAX31855 thermocouple amplifier via SPI.

    The MAX31855 provides temperature readings from a K-type thermocouple
    over a 4-wire SPI interface. This class abstracts the SPI communication
    and data parsing.

    When running on a Raspberry Pi with GPIO support, this communicates over
    actual hardware. In tests, SPI behavior should be mocked.
    """

    def __init__(
        self,
        spi_bus: int = 0,
        spi_device: int = 0,
        max_speed_hz: int = 5_000_000,
    ) -> None:
        """
        Initialize the MAX31855 sensor interface.

        Args:
            spi_bus: SPI bus number (default: 0).
            spi_device: SPI device number on the bus (default: 0).
            max_speed_hz: SPI clock rate in Hz (default: 5000000).

        Note:
            Chip select is managed by the hardware SPI interface.
            Configure CS via device tree or /boot/config.txt on RPi.

        Raises:
            ImportError: If GPIO libraries cannot be imported.
        """
        self.spi_bus = spi_bus
        self.spi_device = spi_device
        self.max_speed_hz = max_speed_hz
        self._spi: Any | None = None

        try:
            spidev_module = import_module("spidev")
            spi = spidev_module.SpiDev()
            spi.open(spi_bus, spi_device)
            spi.max_speed_hz = max_speed_hz
            self._spi = spi
        except ImportError as e:
            raise ImportError(
                "spidev not available. This package only runs on Linux. "
                "Use mocked sensor interfaces for local development and tests."
            ) from e
        except OSError as e:
            raise SensorError(
                f"Failed to open SPI device {spi_bus}:{spi_device}"
            ) from e

    def read_temperature(self) -> tuple[float, float]:
        """
        Read thermocouple and reference junction temperatures.

        Returns:
            Tuple of (thermocouple_temp_celsius, reference_temp_celsius).
            Both values are in degrees Celsius.

        Raises:
            SensorError: If communication fails or sensor fault detected.
        """
        if self._spi is None:
            raise SensorError("SPI device not initialized")

        try:
            data = self._spi.readbytes(4)
        except OSError as e:
            raise SensorError(f"SPI communication error: {e}") from e

        return self._parse_data(data)

    def _parse_data(self, data: list[int]) -> tuple[float, float]:
        """
        Parse raw SPI data from MAX31855.

        The MAX31855 returns 32 bits with temperature data and status.
        Bits 31-18: Thermocouple temperature (14 bits, 0.25C resolution)
        Bits 17-4: Reference junction temperature (14 bits, 0.0625C resolution)
        Bits 3-0: Fault status bits

        Args:
            data: 4-byte array from SPI read.

        Returns:
            Tuple of (thermocouple_temp, reference_temp) in Celsius.

        Raises:
            SensorError: If fault bits indicate an error condition.
        """
        if len(data) != 4:
            raise SensorError(f"Invalid data length: expected 4 bytes, got {len(data)}")

        # Combine 4 bytes into 32-bit value
        raw_value = (data[0] << 24) | (data[1] << 16) | (data[2] << 8) | data[3]

        # Check fault bits (bits 0-3, lower word)
        fault_bits = data[3] & 0x0F
        if fault_bits:
            fault_msg = self._decode_fault(fault_bits)
            raise SensorError(f"Sensor fault detected: {fault_msg}")

        # Extract thermocouple temperature (bits 31-18, shift right 18)
        tc_raw = (raw_value >> 18) & 0x3FFF
        # Handle sign extension for negative temperatures
        if tc_raw & 0x2000:
            tc_raw = -(~(tc_raw - 1) & 0x3FFF)
        tc_temp = tc_raw * 0.25

        # Extract reference temperature (bits 15-4, shift right 4)
        ref_raw = (raw_value >> 4) & 0x0FFF
        # Handle sign extension for negative temperatures
        if ref_raw & 0x0800:
            ref_raw = -(~(ref_raw - 1) & 0x0FFF)
        ref_temp = ref_raw * 0.0625

        return tc_temp, ref_temp

    @staticmethod
    def _decode_fault(fault_bits: int) -> str:
        """
        Decode fault status bits into human-readable form.

        Args:
            fault_bits: The lower 4 bits of the status byte.

        Returns:
            String describing the fault condition.
        """
        if fault_bits & 0x01:
            return "Open circuit (thermocouple not connected)"
        if fault_bits & 0x02:
            return "Short to GND"
        if fault_bits & 0x04:
            return "Short to VCC"
        return f"Unknown fault condition (bits: {fault_bits:04b})"

    def close(self) -> None:
        """Clean up SPI connection resources."""
        if self._spi:
            try:
                self._spi.close()
            except (OSError, AttributeError):
                pass

    def __enter__(self) -> "MAX31855":
        """Context manager entry."""
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> Literal[False]:
        """Context manager exit with cleanup."""
        self.close()
        return False
