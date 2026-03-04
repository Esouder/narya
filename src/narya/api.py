"""
FastAPI REST interface for thermocouple sensor readings.

Provides HTTP endpoints for reading current temperature and health checks.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Optional, Protocol

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from .sensor import SensorError


class SensorProtocol(Protocol):
    """Protocol defining the sensor interface."""

    def read_temperature(self) -> tuple[float, float]:
        """Read temperature from sensor."""

    def close(self) -> None:
        """Close sensor connection."""


class TemperatureReading(BaseModel):
    """
    Thermocouple temperature reading with reference junction data.

    Attributes:
        thermocouple_celsius: Temperature from the thermocouple.
        reference_celsius: Temperature of the reference junction.
    """

    thermocouple_celsius: float
    reference_celsius: float

    @classmethod
    def from_sensor(cls, tc_celsius: float, ref_celsius: float) -> "TemperatureReading":
        """Create reading from sensor data."""
        return cls(
            thermocouple_celsius=tc_celsius,
            reference_celsius=ref_celsius,
        )


class SensorService:
    """
    Service layer managing sensor hardware and configuration.

    This class handles sensor lifecycle, retry logic, and configuration
    management. It abstracts away hardware details from the API layer.
    """

    def __init__(self, sensor: SensorProtocol, max_retries: int = 3):
        """
        Initialize the sensor service.

        Args:
            sensor: Sensor instance implementing the sensor protocol.
            max_retries: Maximum retry attempts on reading failure (default: 3).
        """
        self.sensor = sensor
        self.max_retries = max_retries
        self._last_error: Optional[str] = None

    def read_temperature(self, max_retries: Optional[int] = None) -> TemperatureReading:
        """
        Read thermocouple and reference junction temperatures with retry logic.

        Args:
            max_retries: Override for this read. If None, uses service
                default.

        Returns:
            TemperatureReading with current sensor data.

        Raises:
            SensorError: If all retry attempts fail.
        """
        retries = max_retries if max_retries is not None else self.max_retries
        last_exception: Optional[Exception] = None

        for attempt in range(retries):
            try:
                tc_temp, ref_temp = self.sensor.read_temperature()
                self._last_error = None
                return TemperatureReading.from_sensor(tc_temp, ref_temp)
            except SensorError as e:
                last_exception = e
                if attempt < retries - 1:
                    continue
                self._last_error = str(e)

        raise SensorError(
            f"Failed to read sensor after {retries} attempts: " f"{last_exception}"
        )

    def get_status(self) -> dict[str, bool | str | int | None]:
        """
        Get overall service health status.

        Returns:
            Dictionary with status information including last error.
        """
        return {
            "healthy": self._last_error is None,
            "last_error": self._last_error,
            "max_retries": self.max_retries,
        }

    def close(self) -> None:
        """Clean up SPI sensor connection."""
        self.sensor.close()


def configure_service(sensor: SensorProtocol, max_retries: int = 3) -> None:
    """
    Configure the module-level sensor service used by API endpoints.

    Args:
        sensor: Sensor instance to use.
        max_retries: Maximum retry attempts on read failure.
    """
    app.state.service = SensorService(sensor, max_retries=max_retries)


def _require_service() -> SensorService:
    """Return configured service or raise if application is not initialized."""
    service = getattr(app.state, "service", None)
    if service is None:
        raise HTTPException(status_code=503, detail="Sensor service not configured")
    assert isinstance(service, SensorService)
    return service


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    """Manage application startup/shutdown lifecycle."""
    try:
        yield
    finally:
        service = getattr(app.state, "service", None)
        if service is not None:
            service.close()


app = FastAPI(
    title="Narya",
    description="MAX31855 Thermocouple Reader API",
    version="0.1.0",
    lifespan=lifespan,
)


@app.get("/temperature", response_model=TemperatureReading)
async def get_temperature(max_retries: Optional[int] = None) -> TemperatureReading:
    """
    Read current temperature from thermocouple.

    Args:
        max_retries: Override maximum retry attempts for this read (optional).

    Returns:
        Current temperature reading in Celsius.

    Raises:
        HTTPException: If sensor read fails.
    """
    service = _require_service()
    try:
        return service.read_temperature(max_retries=max_retries)
    except SensorError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e


@app.get("/status")
async def get_status() -> dict[str, bool | str | int | None]:
    """
    Get service health status.

    Returns:
        Status information including health, last error, and config.
    """
    service = _require_service()
    return service.get_status()


@app.get("/health")
async def health_check() -> dict[str, str]:
    """
    Simple health check endpoint.

    Returns:
        Status code 200 if service is running.
    """
    return {"status": "ok"}
