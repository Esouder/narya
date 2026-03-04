FROM python:3.12-slim

LABEL maintainer="Eric <eric@souder.ca>"
LABEL description="Narya - MAX31855 Thermocouple Reader Service"

WORKDIR /app

# Install system dependencies for GPIO and SPI
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy project files
COPY pyproject.toml README.md ./
COPY src ./src

# Install Python dependencies
RUN pip install --no-cache-dir poetry && \
    poetry config virtualenvs.create false && \
    poetry install --only main --no-interaction --no-ansi

# Create non-root user for security
RUN useradd -m -u 1000 narya && \
    chown -R narya:narya /app

USER narya

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health').read()" || exit 1

# Run the application
CMD ["python", "-m", "narya.main", "--host", "0.0.0.0", "--port", "8000"]
