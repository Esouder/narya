"""
FastAPI REST interface for thermocouple sensor readings.

Provides HTTP endpoints for reading current temperature, configuring the
sensor, and retrieving historical readings if enabled.
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
        fahrenheit: Thermocouple temperature in Fahrenheit (computed).
    """

    thermocouple_celsius: float
    reference_celsius: float
    fahrenheit: float

    @classmethod
    def from_sensor(cls, tc_celsius: float, ref_celsius: float) -> "TemperatureReading":
        """Create reading from sensor data."""
        fahrenheit = (tc_celsius * 9 / 5) + 32
        return cls(
            thermocouple_celsius=tc_celsius,
            reference_celsius=ref_celsius,
            fahrenheit=fahrenheit,
        )


class SensorConfig(BaseModel):
    """
    Runtime configuration for the sensor.

    Attributes:
        read_interval_ms: Milliseconds between sensor reads.
        max_retries: Maximum retry attempts on reading failure.
    """

    read_interval_ms: int = 1000
    max_retries: int = 3


class SensorService:
    """
    Service layer managing sensor hardware and configuration.

    This class handles sensor lifecycle, retry logic, and configuration
    management. It abstracts away hardware details from the API layer.
    """

    def __init__(self, sensor: SensorProtocol, config: Optional[SensorConfig] = None):
        """
        Initialize the sensor service.

        Args:
            sensor: Sensor instance implementing the sensor protocol.
            config: Optional configuration. Defaults to standard settings.
        """
        self.sensor = sensor
        self.config = config or SensorConfig()
        self._last_error: Optional[str] = None

    def read_temperature(self) -> TemperatureReading:
        """
        Read current temperature with retry logic.

        Returns:
            TemperatureReading with current sensor data.

        Raises:
            SensorError: If all retry attempts fail.
        """
        last_exception: Optional[Exception] = None

        for attempt in range(self.config.max_retries):
            try:
                tc_temp, ref_temp = self.sensor.read_temperature()
                self._last_error = None
                return TemperatureReading.from_sensor(tc_temp, ref_temp)
            except SensorError as e:
                last_exception = e
                if attempt < self.config.max_retries - 1:
                    continue
                self._last_error = str(e)

        raise SensorError(
            f"Failed to read sensor after {self.config.max_retries} attempts: "
            f"{last_exception}"
        )

    def get_status(self) -> dict[str, bool | str | int | None]:
        """
        Get overall service status.

        Returns:
            Dictionary with status information including last error if any.
        """
        return {
            "healthy": self._last_error is None,
            "last_error": self._last_error,
            "read_interval_ms": self.config.read_interval_ms,
            "max_retries": self.config.max_retries,
        }

    def update_config(self, config: SensorConfig) -> None:
        """
        Update sensor configuration at runtime.

        Args:
            config: New configuration to apply.
        """
        self.config = config

    def close(self) -> None:
        """Clean up sensor resources."""
        self.sensor.close()


def configure_service(
    sensor: SensorProtocol, config: Optional[SensorConfig] = None
) -> None:
    """Configure the module-level sensor service used by API endpoints."""
    app.state.service = SensorService(sensor, config)


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
async def get_temperature() -> TemperatureReading:
    """
    Read current temperature from thermocouple.

    Returns:
        Current temperature reading in Celsius and Fahrenheit.

    Raises:
        HTTPException: If sensor read fails.
    """
    service = _require_service()
    try:
        return service.read_temperature()
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


@app.post("/config")
async def update_config(config: SensorConfig) -> dict[str, str | SensorConfig]:
    """
    Update sensor configuration at runtime.

    Args:
        config: New configuration to apply.

    Returns:
        Confirmation of updated configuration.
    """
    service = _require_service()
    service.update_config(config)
    return {"message": "Configuration updated", "config": config}


@app.get("/health")
async def health_check() -> dict[str, str]:
    """
    Simple health check endpoint.

    Returns:
        Status code 200 if service is running.
    """
    return {"status": "ok"}
