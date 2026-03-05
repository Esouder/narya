"""
Main application entry point for the Narya thermocouple service.

Configures and starts the FastAPI server with runtime parameters
passed via command-line arguments.
"""

import argparse
import logging
import sys
from dataclasses import dataclass
from typing import Optional

import uvicorn

from .api import app, configure_service
from .sensor import MAX31855


@dataclass(frozen=True)
class AppArgs:  # pylint: disable=too-many-instance-attributes
    """Typed runtime arguments for the application."""

    spi_bus: int
    spi_device: int
    max_speed_hz: int
    max_retries: int
    host: str
    port: int
    workers: int
    log_level: str


def setup_logging(level: str = "INFO") -> None:
    """
    Configure application logging.

    Args:
        level: Logging level (DEBUG, INFO, WARNING, ERROR).
    """
    logging.basicConfig(
        level=getattr(logging, level.upper()),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )


def parse_arguments() -> AppArgs:
    """
    Parse command-line arguments.

    Returns:
        Parsed arguments namespace.
    """
    parser = argparse.ArgumentParser(
        description="Narya - MAX31855 Thermocouple Reader Service",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Standard deployment on Raspberry Pi
  python -m narya.main --host 0.0.0.0 --port 8000

  # With custom SPI clock rate
  python -m narya.main --spi-clock-hz 1000000 --host 0.0.0.0
        """,
    )

    # Hardware configuration
    parser.add_argument(
        "--spi-bus",
        type=int,
        default=0,
        help="SPI bus number (default: 0)",
    )
    parser.add_argument(
        "--spi-device",
        type=int,
        default=0,
        help="SPI device number (default: 0)",
    )
    parser.add_argument(
        "--spi-clock-hz",
        type=int,
        default=5_000_000,
        help="SPI clock rate in Hz (default: 5000000)",
    )

    # Sensor configuration
    parser.add_argument(
        "--max-retries",
        type=int,
        default=3,
        help="Maximum retry attempts on read failure (default: 3)",
    )

    # Server configuration
    parser.add_argument(
        "--host",
        type=str,
        default="127.0.0.1",
        help="API server host (default: 127.0.0.1)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="API server port (default: 8000)",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=1,
        help="Number of worker processes (default: 1)",
    )

    # Runtime options
    parser.add_argument(
        "--log-level",
        type=str,
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging level (default: INFO)",
    )

    namespace = parser.parse_args()
    return AppArgs(
        spi_bus=namespace.spi_bus,
        spi_device=namespace.spi_device,
        max_speed_hz=namespace.spi_clock_hz,
        max_retries=namespace.max_retries,
        host=namespace.host,
        port=namespace.port,
        workers=namespace.workers,
        log_level=namespace.log_level,
    )


def main(args: Optional[AppArgs] = None) -> int:
    """
    Initialize and start the Narya service.

    Args:
        args: Parsed command-line arguments. If None, arguments are
            parsed from sys.argv.

    Returns:
        Exit code (0 for success, 1 for failure).
    """
    parsed_args: AppArgs = args if args is not None else parse_arguments()

    setup_logging(parsed_args.log_level)
    logger = logging.getLogger(__name__)

    try:
        logger.info("Initializing MAX31855 sensor...")
        sensor = MAX31855(
            spi_bus=parsed_args.spi_bus,
            spi_device=parsed_args.spi_device,
            max_speed_hz=parsed_args.max_speed_hz,
        )

        # Verify sensor connectivity with a test read
        tc_temp, ref_temp = sensor.read_temperature()
        logger.info(
            "Sensor initialized successfully. TC: %.2fC, Ref: %.2fC",
            tc_temp,
            ref_temp,
        )

        logger.info("Configuring FastAPI application...")
        configure_service(sensor, max_retries=parsed_args.max_retries)

        logger.info(
            "Starting server on %s:%s with %s worker(s)",
            parsed_args.host,
            parsed_args.port,
            parsed_args.workers,
        )
        uvicorn.run(
            app,
            host=parsed_args.host,
            port=parsed_args.port,
            workers=parsed_args.workers,
            log_level=parsed_args.log_level.lower(),
        )

        return 0

    except KeyboardInterrupt:
        logger.info("Shutdown requested by user")
        return 0
    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.error("Fatal error: %s", e, exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
