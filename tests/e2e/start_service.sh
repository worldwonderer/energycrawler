#!/bin/bash
# Start Energy Service Script
# Run this script in a terminal with GUI access to start the Energy service manually

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
ENERGY_SERVICE_DIR="/Users/pite/EnergyCrawler/energy-service"
ENERGY_SERVICE_BIN="${ENERGY_SERVICE_DIR}/energy-service"

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

# Check if service directory exists
if [ ! -d "$ENERGY_SERVICE_DIR" ]; then
    log_error "Energy service directory not found: $ENERGY_SERVICE_DIR"
    exit 1
fi

# Check if binary exists
if [ ! -f "$ENERGY_SERVICE_BIN" ]; then
    log_warn "Energy service binary not found at $ENERGY_SERVICE_BIN"
    log_info "Attempting to build..."
    cd "$ENERGY_SERVICE_DIR"

    if [ ! -f "go.mod" ]; then
        log_error "go.mod not found in $ENERGY_SERVICE_DIR"
        exit 1
    fi

    if ! go build -o energy-service .; then
        log_error "Failed to build Energy service"
        exit 1
    fi

    log_info "Energy service built successfully"
fi

# Start the service
log_info "Starting Energy service..."
log_info "Service directory: $ENERGY_SERVICE_DIR"
log_info "Press Ctrl+C to stop the service"
echo ""

cd "$ENERGY_SERVICE_DIR"
exec ./energy-service
