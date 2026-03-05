#!/bin/bash
# Dynamic entrypoint that builds command from environment variables

# Default values
SPI_BUS=${SPI_BUS:-0}
SPI_DEVICE=${SPI_DEVICE:-0}
SPI_CLOCK_HZ=${SPI_CLOCK_HZ:-5000000}
MAX_RETRIES=${MAX_RETRIES:-3}
HOST=${HOST:-0.0.0.0}
PORT=${PORT:-8000}
WORKERS=${WORKERS:-1}
LOG_LEVEL=${LOG_LEVEL:-INFO}

# Build command
exec python -m narya.main \
    --spi-bus "$SPI_BUS" \
    --spi-device "$SPI_DEVICE" \
    --spi-clock-hz "$SPI_CLOCK_HZ" \
    --max-retries "$MAX_RETRIES" \
    --host "$HOST" \
    --port "$PORT" \
    --workers "$WORKERS" \
    --log-level "$LOG_LEVEL"
