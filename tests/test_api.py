"""Tests for the API module."""

from __future__ import annotations

from typing import Any, TypeGuard

import pytest
from fastapi.testclient import TestClient
from httpx import Response

from narya import api
from narya.api import SensorConfig, SensorService, TemperatureReading
from narya.sensor import SensorError


class FakeSensor:
    """Typed fake sensor used in API tests."""

    def __init__(
        self,
        reading: tuple[float, float] = (25.0, 25.0),
        fail: bool = False,
    ) -> None:
        self.reading = reading
        self.fail = fail
        self.closed = False

    def read_temperature(self) -> tuple[float, float]:
        if self.fail:
            raise SensorError("read failed")
        return self.reading

    def close(self) -> None:
        self.closed = True


def _is_string_keyed_dict(value: Any) -> TypeGuard[dict[str, Any]]:
    """Type guard to narrow Any to dict[str, Any]."""
    return isinstance(value, dict)


def _response_json(response: Response) -> dict[str, Any]:
    payload = response.json()
    if not _is_string_keyed_dict(payload):
        raise AssertionError(f"Expected dict, got {type(payload)}: {payload}")
    return payload


@pytest.fixture(name="client")
def fixture_client() -> TestClient:
    """Return a test client with configured sensor service."""
    api.configure_service(FakeSensor())
    return TestClient(api.app)


class TestTemperatureReading:
    """Test TemperatureReading model."""

    def test_temperature_reading_creation(self) -> None:
        reading = TemperatureReading(
            thermocouple_celsius=25.0,
            reference_celsius=25.0,
            fahrenheit=77.0,
        )
        assert reading.thermocouple_celsius == 25.0
        assert reading.reference_celsius == 25.0
        assert reading.fahrenheit == 77.0

    def test_temperature_reading_from_sensor(self) -> None:
        reading = TemperatureReading.from_sensor(25.0, 25.0)
        assert abs(reading.fahrenheit - 77.0) < 0.1


class TestSensorService:
    """Test SensorService behavior."""

    def test_service_read_success(self) -> None:
        service = SensorService(FakeSensor())
        reading = service.read_temperature()

        assert isinstance(reading, TemperatureReading)
        assert reading.thermocouple_celsius == 25.0

    def test_service_retries_then_fails(self) -> None:
        service = SensorService(FakeSensor(fail=True), SensorConfig(max_retries=2))

        with pytest.raises(SensorError, match="Failed to read sensor after 2 attempts"):
            service.read_temperature()

    def test_service_status(self) -> None:
        service = SensorService(FakeSensor())
        status = service.get_status()

        assert status["healthy"] is True
        assert status["read_interval_ms"] == 1000


class TestAPIEndpoints:
    """Test module-level FastAPI endpoints."""

    def test_health_endpoint(self, client: TestClient) -> None:
        response = client.get("/health")
        assert response.status_code == 200
        assert _response_json(response)["status"] == "ok"

    def test_temperature_endpoint(self, client: TestClient) -> None:
        response = client.get("/temperature")

        assert response.status_code == 200
        payload = _response_json(response)
        assert payload["thermocouple_celsius"] == 25.0
        assert payload["reference_celsius"] == 25.0

    def test_status_endpoint(self, client: TestClient) -> None:
        response = client.get("/status")

        assert response.status_code == 200
        payload = _response_json(response)
        assert payload["healthy"] is True

    def test_config_endpoint(self, client: TestClient) -> None:
        response = client.post(
            "/config", json={"read_interval_ms": 500, "max_retries": 5}
        )

        assert response.status_code == 200
        payload = _response_json(response)
        assert payload["config"]["read_interval_ms"] == 500

    def test_temperature_failure_returns_503(self) -> None:
        api.configure_service(FakeSensor(fail=True))
        client = TestClient(api.app)

        response = client.get("/temperature")

        assert response.status_code == 503
        assert "read failed" in _response_json(response)["detail"]

    def test_unconfigured_service_returns_503(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delattr(api.app.state, "service", raising=False)
        client = TestClient(api.app)

        response = client.get("/temperature")

        assert response.status_code == 503
        assert "not configured" in _response_json(response)["detail"]
