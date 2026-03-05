"""Tests for the main module."""

from __future__ import annotations

import sys
from unittest.mock import Mock, patch

import pytest  # pylint: disable=import-error

from narya.main import AppArgs, main, parse_arguments, setup_logging


class TestArgumentParsing:
    """Test command-line argument parsing."""

    def test_parse_arguments_defaults(self) -> None:
        with patch.object(sys, "argv", ["narya"]):
            args = parse_arguments()

        assert args.spi_bus == 0
        assert args.spi_device == 0
        assert args.max_retries == 3
        assert args.host == "127.0.0.1"
        assert args.port == 8000
        assert args.workers == 1
        assert args.log_level == "INFO"

    def test_parse_arguments_custom_values(self) -> None:
        with patch.object(
            sys,
            "argv",
            [
                "narya",
                "--spi-bus",
                "1",
                "--spi-device",
                "0",
                "--max-retries",
                "5",
                "--host",
                "0.0.0.0",
                "--port",
                "8080",
                "--workers",
                "2",
                "--log-level",
                "DEBUG",
            ],
        ):
            args = parse_arguments()

        assert args.spi_bus == 1
        assert args.spi_device == 0
        assert args.max_retries == 5
        assert args.host == "0.0.0.0"
        assert args.port == 8080
        assert args.workers == 2
        assert args.log_level == "DEBUG"

    def test_invalid_log_level_rejected(self) -> None:
        with patch.object(sys, "argv", ["narya", "--log-level", "INVALID"]):
            with pytest.raises(SystemExit):
                parse_arguments()


class TestLogging:
    """Test logging setup."""

    def test_setup_logging_levels(self) -> None:
        for level in ["DEBUG", "INFO", "WARNING", "ERROR"]:
            setup_logging(level)

    def test_setup_logging_default(self) -> None:
        setup_logging()


class TestMainFunction:
    """Test main runtime flow."""

    def _app_args(self) -> AppArgs:
        return AppArgs(
            spi_bus=0,
            spi_device=0,
            max_speed_hz=5_000_000,
            max_retries=3,
            host="127.0.0.1",
            port=8000,
            workers=1,
            log_level="INFO",
        )

    def test_main_success(self) -> None:
        args = self._app_args()
        fake_sensor = Mock()
        fake_sensor.read_temperature.return_value = (25.0, 25.0)

        with (
            patch("narya.main.MAX31855", return_value=fake_sensor),
            patch("narya.main.configure_service") as configure_service,
            patch("narya.main.uvicorn.run") as uvicorn_run,
        ):
            result = main(args)

        assert result == 0
        configure_service.assert_called_once()
        uvicorn_run.assert_called_once()

    def test_main_keyboard_interrupt(self) -> None:
        args = self._app_args()
        fake_sensor = Mock()
        fake_sensor.read_temperature.return_value = (25.0, 25.0)

        with (
            patch("narya.main.MAX31855", return_value=fake_sensor),
            patch("narya.main.configure_service"),
            patch("narya.main.uvicorn.run", side_effect=KeyboardInterrupt),
        ):
            result = main(args)

        assert result == 0

    def test_main_generic_error(self) -> None:
        args = self._app_args()

        with patch("narya.main.MAX31855", side_effect=RuntimeError("boom")):
            result = main(args)

        assert result == 1
