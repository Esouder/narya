"""Tests for the sensor module."""

from __future__ import annotations

import types

import pytest

from narya.sensor import MAX31855, SensorError


class FakeSpiDev:
    """Fake SPI implementation with configurable read payload."""

    payload: list[int] = [0x01, 0x90, 0x19, 0x00]
    fail_read = False
    fail_open = False
    fail_close = False

    def __init__(self) -> None:
        self.max_speed_hz: int | None = None
        self.opened: tuple[int, int] | None = None
        self.closed = False

    def open(self, bus: int, device: int) -> None:
        if self.fail_open:
            raise OSError("cannot open spi")
        self.opened = (bus, device)

    def readbytes(self, count: int) -> list[int]:
        if self.fail_read:
            raise OSError("read failed")
        return self.payload[:count]

    def close(self) -> None:
        if self.fail_close:
            raise OSError("close failed")
        self.closed = True


def _patch_spidev(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_module = types.SimpleNamespace(SpiDev=FakeSpiDev)

    def fake_import(_: str) -> types.SimpleNamespace:
        return fake_module

    monkeypatch.setattr("narya.sensor.import_module", fake_import)


class TestMAX31855Initialization:
    """Test sensor initialization and SPI setup."""

    def test_init_success(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_spidev(monkeypatch)

        sensor = MAX31855(spi_bus=1, spi_device=0)

        assert sensor.spi_bus == 1
        assert sensor.spi_device == 0

    def test_init_import_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def raise_import_error(_: str) -> None:
            raise ImportError("No module named spidev")

        monkeypatch.setattr("narya.sensor.import_module", raise_import_error)

        with pytest.raises(ImportError, match="spidev not available"):
            MAX31855()

    def test_init_open_failure(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_spidev(monkeypatch)
        FakeSpiDev.fail_open = True

        try:
            with pytest.raises(SensorError, match="Failed to open SPI device"):
                MAX31855(spi_bus=0, spi_device=0)
        finally:
            FakeSpiDev.fail_open = False


class TestTemperatureReading:
    """Test temperature reading and parser behavior through public API."""

    def test_read_temperature_success(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_spidev(monkeypatch)
        FakeSpiDev.payload = [0x01, 0x90, 0x19, 0x00]

        sensor = MAX31855()
        tc_temp, ref_temp = sensor.read_temperature()

        assert tc_temp == 25.0
        assert ref_temp == 25.0

    def test_read_temperature_invalid_payload(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch_spidev(monkeypatch)
        FakeSpiDev.payload = [0x00, 0x00, 0x00]

        sensor = MAX31855()

        with pytest.raises(SensorError, match="Invalid data length"):
            sensor.read_temperature()

    def test_read_temperature_spi_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_spidev(monkeypatch)
        FakeSpiDev.fail_read = True

        try:
            sensor = MAX31855()
            with pytest.raises(SensorError, match="SPI communication error"):
                sensor.read_temperature()
        finally:
            FakeSpiDev.fail_read = False

    def test_read_temperature_faults(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_spidev(monkeypatch)
        sensor = MAX31855()

        for payload, message in [
            ([0x00, 0x00, 0x00, 0x01], "Open circuit"),
            ([0x00, 0x00, 0x00, 0x02], "Short to GND"),
            ([0x00, 0x00, 0x00, 0x04], "Short to VCC"),
            ([0x00, 0x00, 0x00, 0x08], "Unknown fault"),
        ]:
            FakeSpiDev.payload = payload
            with pytest.raises(SensorError, match=message):
                sensor.read_temperature()


class TestCleanupAndContext:
    """Test cleanup and context manager behavior."""

    def test_close_ignores_oserror(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_spidev(monkeypatch)
        FakeSpiDev.fail_close = True

        try:
            sensor = MAX31855()
            sensor.close()
        finally:
            FakeSpiDev.fail_close = False

    def test_context_manager(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_spidev(monkeypatch)

        with MAX31855() as sensor:
            assert isinstance(sensor, MAX31855)


class TestSensorError:
    """Test SensorError basics."""

    def test_sensor_error_inheritance(self) -> None:
        error = SensorError("test")
        assert isinstance(error, Exception)
        assert str(error) == "test"

    def test_sensor_error_message(self) -> None:
        error = SensorError("sensor failure")
        assert "sensor failure" in str(error)
