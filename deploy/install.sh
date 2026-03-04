#!/bin/bash

set -e

# Narya Installation Script for Raspberry Pi
# This script installs the Narya thermocouple reader service on a target machine
# 
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/Esouder/narya/master/deploy/install.sh | sudo bash
#   
# Or with custom image:
#   curl -fsSL https://raw.githubusercontent.com/Esouder/narya/master/deploy/install.sh | sudo NARYA_IMAGE=ghcr.io/user/narya:latest bash

VERSION="0.1.0"
INSTALL_DIR="/opt/narya"
SERVICE_NAME="narya"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"
REGISTRY="ghcr.io"
IMAGE_NAME="narya"

# GitHub raw content base URL (override with GITHUB_BASE_URL env var)
GITHUB_BASE_URL="${GITHUB_BASE_URL:-https://raw.githubusercontent.com/Esouder/narya/master/deploy}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Logging functions
log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if running as root
check_root() {
    if [[ $EUID -ne 0 ]]; then
        log_error "This script must be run as root"
        exit 1
    fi
}

# Check prerequisites
check_prerequisites() {
    log_info "Checking prerequisites..."

    if ! command -v docker &> /dev/null; then
        log_error "Docker is not installed"
        exit 1
    fi
    log_info "Docker found: $(docker --version)"

    if ! command -v docker-compose &> /dev/null; then
        log_error "Docker Compose is not installed"
        exit 1
    fi
    log_info "Docker Compose found: $(docker-compose --version)"

    # Check if user has docker group access
    if ! groups | grep -q docker; then
        log_warn "Current user is not in docker group. You may need to use 'sudo' or add user to docker group"
    fi
}

# Download deployment files from GitHub
download_files() {
    log_info "Downloading deployment files from GitHub..."

    if ! command -v curl &> /dev/null; then
        log_error "curl is required but not installed"
        exit 1
    fi

    # Download docker-compose.yml
    if curl -fsSL "${GITHUB_BASE_URL}/docker-compose.yml" -o "$INSTALL_DIR/docker-compose.yml"; then
        log_info "Downloaded docker-compose.yml"
    else
        log_error "Failed to download docker-compose.yml from ${GITHUB_BASE_URL}"
        exit 1
    fi

    # Download systemd service file to temp location
    if curl -fsSL "${GITHUB_BASE_URL}/narya.service" -o "/tmp/narya.service"; then
        log_info "Downloaded narya.service"
    else
        log_error "Failed to download narya.service from ${GITHUB_BASE_URL}"
        exit 1
    fi
}

# Create installation directory
setup_directories() {
    log_info "Setting up installation directory at ${INSTALL_DIR}..."

    if [ ! -d "$INSTALL_DIR" ]; then
        mkdir -p "$INSTALL_DIR"
        chmod 755 "$INSTALL_DIR"
        log_info "Created ${INSTALL_DIR}"
    else
        log_warn "${INSTALL_DIR} already exists"
    fi
}

# Install systemd service
install_systemd_service() {
    log_info "Installing systemd service..."

    if [ ! -f "/tmp/narya.service" ]; then
        log_error "/tmp/narya.service not found"
        exit 1
    fi

    cp /tmp/narya.service "$SERVICE_FILE"
    chmod 644 "$SERVICE_FILE"

    # Update the service file with actual image name (allow for custom registry)
    if [ -n "$REGISTRY_OVERRIDE" ]; then
        sed -i "s|ghcr.io/esouder/narya|$REGISTRY_OVERRIDE/narya|g" "$SERVICE_FILE"
    fi

    systemctl daemon-reload
    log_info "Systemd service installed at ${SERVICE_FILE}"
    
    # Clean up temp file
    rm -f /tmp/narya.service
}

# Configure hardware access
setup_hardware_access() {
    log_info "Configuring hardware access..."

    # Add docker user to gpio/spi groups if they exist
    if groups | grep -q gpio; then
        if ! id -Gn docker | grep -q gpio; then
            usermod -a -G gpio docker 2>/dev/null || true
            log_info "Added docker user to gpio group"
        fi
    fi

    if groups | grep -q spi; then
        if ! id -Gn docker | grep -q spi; then
            usermod -a -G spi docker 2>/dev/null || true
            log_info "Added docker user to spi group"
        fi
    fi
}

# Pull the container image
pull_image() {
    log_info "Pulling container image..."

    IMAGE="${REGISTRY}/esouder/${IMAGE_NAME}:latest"
    # Allow override via environment variable
    if [ -n "$NARYA_IMAGE" ]; then
        IMAGE="$NARYA_IMAGE"
    fi

    docker pull "$IMAGE" || {
        log_error "Failed to pull image: $IMAGE"
        log_warn "Ensure the image exists in the registry and you have proper credentials"
        exit 1
    }
    log_info "Successfully pulled $IMAGE"
}

# Start the service
start_service() {
    log_info "Starting narya service..."

    if systemctl start "$SERVICE_NAME"; then
        log_info "Service started successfully"
    else
        log_error "Failed to start service"
        log_info "Check logs with: journalctl -u ${SERVICE_NAME} -n 50"
        exit 1
    fi

    # Enable service to start on boot
    systemctl enable "$SERVICE_NAME"
    log_info "Service enabled for automatic startup"
}

# Verify installation
verify_installation() {
    log_info "Verifying installation..."

    sleep 2

    if systemctl is-active --quiet "$SERVICE_NAME"; then
        log_info "Service is running"

        # Try to access the health endpoint
        if command -v curl &> /dev/null; then
            if curl -s http://localhost:8000/health > /dev/null 2>&1; then
                log_info "Health check passed!"
            else
                log_warn "Could not reach health endpoint (service may still be starting)"
            fi
        fi
    else
        log_error "Service is not running"
        log_info "Check logs with: journalctl -u ${SERVICE_NAME} -n 50"
        exit 1
    fi
}

# Show status and next steps
show_status() {
    echo ""
    log_info "Installation complete!"
    echo ""
    echo "Next steps:"
    echo "  1. Review configuration: cat ${INSTALL_DIR}/docker-compose.yml"
    echo "  2. Check service status: systemctl status ${SERVICE_NAME}"
    echo "  3. View logs: journalctl -u ${SERVICE_NAME} -f"
    echo "  4. Access API: curl http://localhost:8000/temperature"
    echo ""
    echo "Common commands:"
    echo "  Start service:  systemctl start ${SERVICE_NAME}"
    echo "  Stop service:   systemctl stop ${SERVICE_NAME}"
    echo "  Restart service: systemctl restart ${SERVICE_NAME}"
    echo "  View logs:      journalctl -u ${SERVICE_NAME} -f"
    echo ""
}

# Main installation flow
main() {
    echo "Narya Installation Script v${VERSION}"
    echo "=================================="
    echo ""

    check_root
    check_prerequisites
    setup_directories
    download_files
    setup_hardware_access
    pull_image
    install_systemd_service
    start_service
    verify_installation
    show_status
}

# Run main function
main "$@"
