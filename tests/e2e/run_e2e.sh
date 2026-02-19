#!/bin/bash
# E2E Test Runner Script
# This script starts the Energy service, runs E2E tests, and cleans up.

set -e

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
ENERGY_SERVICE_DIR="${PROJECT_ROOT}/energy-service"
ENERGY_SERVICE_BIN="${ENERGY_SERVICE_DIR}/energy-service"
E2E_TEST_DIR="${PROJECT_ROOT}/tests/e2e"
ENERGY_CLIENT_DIR="${PROJECT_ROOT}/energy_client"
COVERAGE_DIR="${PROJECT_ROOT}/coverage"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
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

log_debug() {
    echo -e "${BLUE}[DEBUG]${NC} $1"
}

# Cleanup function
cleanup() {
    local exit_code=$?

    log_info "Cleaning up..."

    # Kill service if running
    if [ ! -z "$SERVICE_PID" ]; then
        log_info "Stopping Energy service (PID: $SERVICE_PID)..."
        kill $SERVICE_PID 2>/dev/null || true
        wait $SERVICE_PID 2>/dev/null || true
    fi

    # Kill any remaining energy-service processes started by this script
    pkill -f "energy-service" 2>/dev/null || true

    # Clean up temporary files
    rm -f /tmp/energy_service_*.log 2>/dev/null || true

    exit $exit_code
}

# Set up cleanup on exit
trap cleanup EXIT INT TERM

# Check prerequisites
check_prerequisites() {
    log_info "Checking prerequisites..."

    local missing_deps=()

    # Check Go
    if ! command -v go &> /dev/null; then
        missing_deps+=("Go 1.21+")
    else
        local go_version=$(go version | grep -oP 'go\K[0-9.]+' | head -1)
        log_debug "Found Go version: $go_version"
    fi

    # Check Python
    if ! command -v python3 &> /dev/null; then
        missing_deps+=("Python 3.10+")
    else
        local py_version=$(python3 --version 2>&1 | grep -oP '\d+\.\d+')
        log_debug "Found Python version: $py_version"
    fi

    # Check pytest
    if ! python3 -m pytest --version &> /dev/null; then
        missing_deps+=("pytest (pip install pytest)")
    fi

    # Check grpcio
    if ! python3 -c "import grpc" &> /dev/null 2>&1; then
        missing_deps+=("grpcio (pip install grpcio grpcio-tools)")
    fi

    # Check pytest-cov (optional, for coverage)
    if ! python3 -c "import pytest_cov" &> /dev/null 2>&1; then
        log_warn "pytest-cov not installed - coverage will be disabled"
        COVERAGE_ENABLED=false
    else
        COVERAGE_ENABLED=true
    fi

    # Check if energy_client module exists
    if [ ! -d "$ENERGY_CLIENT_DIR" ]; then
        missing_deps+=("energy_client directory")
    fi

    # Report missing dependencies
    if [ ${#missing_deps[@]} -gt 0 ]; then
        log_error "Missing dependencies:"
        for dep in "${missing_deps[@]}"; do
            echo "  - $dep"
        done
        echo ""
        echo "Please install missing dependencies and try again."
        exit 1
    fi

    log_info "All prerequisites satisfied."
}

# Build Energy service
build_service() {
    log_info "Building Energy service..."

    if [ ! -d "$ENERGY_SERVICE_DIR" ]; then
        log_error "Energy service directory not found: $ENERGY_SERVICE_DIR"
        exit 1
    fi

    cd "$ENERGY_SERVICE_DIR"

    # Check for Go module
    if [ ! -f "go.mod" ]; then
        log_error "go.mod not found in $ENERGY_SERVICE_DIR"
        exit 1
    fi

    # Build with version info
    local build_time=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
    local git_commit=$(git rev-parse --short HEAD 2>/dev/null || echo "unknown")

    log_debug "Building with commit: $git_commit"

    if ! go build -ldflags "-X main.Version=$git_commit -X main.BuildTime=$build_time" -o energy-service .; then
        log_error "Failed to build Energy service"
        exit 1
    fi

    if [ ! -f "$ENERGY_SERVICE_BIN" ]; then
        log_error "Energy service binary not found after build"
        exit 1
    fi

    log_info "Energy service built successfully: $ENERGY_SERVICE_BIN"
}

# Start Energy service
start_service() {
    log_info "Starting Energy service..."

    cd "$ENERGY_SERVICE_DIR"

    # Create log file
    local log_file="/tmp/energy_service_$$.log"

    # Start in background with logging
    export ENERGY_SERVICE_PORT=${ENERGY_SERVICE_PORT:-50051}
    "$ENERGY_SERVICE_BIN" > "$log_file" 2>&1 &
    SERVICE_PID=$!

    log_info "Energy service started (PID: $SERVICE_PID)"
    log_debug "Log file: $log_file"

    # Wait for service to be ready
    log_info "Waiting for service to be ready..."
    local max_attempts=30
    local attempt=1

    while [ $attempt -le $max_attempts ]; do
        if python3 -c "
import grpc
import sys
sys.path.insert(0, '$ENERGY_CLIENT_DIR')
from energy_client import browser_pb2_grpc
channel = grpc.insecure_channel('localhost:${ENERGY_SERVICE_PORT}')
stub = browser_pb2_grpc.BrowserServiceStub(channel)
channel.close()
" 2>/dev/null; then
            log_info "Service is ready! (attempt $attempt/$max_attempts)"
            return 0
        fi

        log_debug "Attempt $attempt/$max_attempts - waiting for service..."

        # Check if process is still alive
        if ! kill -0 $SERVICE_PID 2>/dev/null; then
            log_error "Service process died unexpectedly"
            log_error "Last 20 lines of log:"
            tail -20 "$log_file" 2>/dev/null || true
            return 1
        fi

        sleep 1
        attempt=$((attempt + 1))
    done

    log_error "Service failed to start within timeout"
    log_error "Last 20 lines of log:"
    tail -20 "$log_file" 2>/dev/null || true
    return 1
}

# Run E2E tests
run_tests() {
    log_info "Running E2E tests..."

    cd "$PROJECT_ROOT"

    # Create coverage directory
    mkdir -p "$COVERAGE_DIR"

    # Set environment variables for tests
    export ENERGY_SERVICE_HOST="localhost"
    export ENERGY_SERVICE_PORT="${ENERGY_SERVICE_PORT:-50051}"
    export SERVICE_STARTUP_TIMEOUT="30"

    # Check if service is running
    log_info "Checking if Energy service is running..."
    if ! python3 -c "
import grpc
import sys
sys.path.insert(0, '$ENERGY_CLIENT_DIR')
from energy_client import browser_pb2_grpc
channel = grpc.insecure_channel('localhost:${ENERGY_SERVICE_PORT}')
stub = browser_pb2_grpc.BrowserServiceStub(channel)
channel.close()
" 2>/dev/null; then
        log_warn "Energy service is not running!"
        echo ""
        echo "Please start the Energy service manually in a separate terminal:"
        echo "  cd $ENERGY_SERVICE_DIR && ./energy-service"
        echo ""
        echo "Or use the provided script:"
        echo "  bash ${E2E_TEST_DIR}/start_service.sh"
        echo ""
        echo "After starting the service, run this script again."
        exit 1
    fi

    log_info "Energy service is running!"

    # Build pytest arguments
    local pytest_args=(
        "-v"                          # Verbose output
        "-s"                          # Show print statements
        "--tb=short"                  # Short traceback format
        "-m" "e2e"                    # Run only e2e tests
        "--color=yes"                 # Colored output
        "--durations=10"              # Show 10 slowest tests
    )

    # Add coverage if enabled
    if [ "$COVERAGE_ENABLED" = true ]; then
        pytest_args+=(
            "--cov=energy_client"
            "--cov-report=term-missing"
            "--cov-report=html:$COVERAGE_DIR/htmlcov"
            "--cov-fail-under=0"      # Don't fail on low coverage
        )
    fi

    # Add extra arguments if provided
    if [ ! -z "$@" ]; then
        pytest_args+=("$@")
    fi

    # Run tests
    cd "$E2E_TEST_DIR"
    log_info "Running: python3 -m pytest ${pytest_args[*]}"

    if python3 -m pytest "${pytest_args[@]}"; then
        log_info "E2E tests completed successfully!"
        if [ "$COVERAGE_ENABLED" = true ]; then
            log_info "Coverage report: $COVERAGE_DIR/htmlcov/index.html"
        fi
        return 0
    else
        log_error "E2E tests failed"
        return 1
    fi
}

# Run specific test file
run_specific_test() {
    local test_file=$1
    shift

    log_info "Running specific test: $test_file"

    cd "$PROJECT_ROOT"

    export ENERGY_SERVICE_HOST="localhost"
    export ENERGY_SERVICE_PORT="${ENERGY_SERVICE_PORT:-50051}"

    cd "$E2E_TEST_DIR"
    python3 -m pytest "$test_file" -v -s --tb=short "$@"
}

# Run all tests (not just e2e)
run_all_tests() {
    log_info "Running all tests..."

    cd "$PROJECT_ROOT"

    # Run Go tests
    log_info "Running Go unit tests..."
    cd "$ENERGY_SERVICE_DIR"
    if ! go test ./... -v -coverprofile="$COVERAGE_DIR/go_coverage.out"; then
        log_error "Go tests failed"
        return 1
    fi
    log_info "Go tests passed"

    # Run Python unit tests
    log_info "Running Python unit tests..."
    cd "$ENERGY_CLIENT_DIR"
    if ! python3 -m pytest tests/ -v --tb=short; then
        log_error "Python tests failed"
        return 1
    fi
    log_info "Python tests passed"

    # Run E2E tests
    run_tests || return 1

    log_info "All tests passed!"
    return 0
}

# Show test list
show_test_list() {
    log_info "Available E2E tests:"
    cd "$E2E_TEST_DIR"
    python3 -m pytest --collect-only -q 2>/dev/null | grep "test_" || true
}

# Main function
main() {
    local command=${1:-"e2e"}

    case $command in
        "build")
            check_prerequisites
            build_service
            ;;
        "start")
            check_prerequisites
            build_service
            start_service
            log_info "Service is running. Press Ctrl+C to stop."
            log_info "Service PID: $SERVICE_PID"
            wait $SERVICE_PID
            ;;
        "e2e")
            check_prerequisites
            run_tests "${@:2}"
            ;;
        "test")
            check_prerequisites
            run_specific_test "${@:2}"
            ;;
        "all")
            check_prerequisites
            build_service
            start_service
            run_all_tests
            ;;
        "list")
            show_test_list
            ;;
        "quick")
            # Quick test run - skip slow tests
            check_prerequisites
            run_tests "${@:2}" -m "e2e and not slow"
            ;;
        "help"|"-h"|"--help")
            echo "Usage: $0 [command] [options]"
            echo ""
            echo "Commands:"
            echo "  build    Build the Energy service"
            echo "  start    Start the Energy service (runs until Ctrl+C)"
            echo "  e2e      Build, start service, and run E2E tests (default)"
            echo "  test     Run a specific test file"
            echo "  all      Run all tests (Go, Python unit, and E2E)"
            echo "  list     List all available E2E tests"
            echo "  quick    Run E2E tests excluding slow tests"
            echo "  help     Show this help message"
            echo ""
            echo "Options:"
            echo "  Any additional arguments are passed to pytest"
            echo ""
            echo "Examples:"
            echo "  $0                           # Run all E2E tests"
            echo "  $0 e2e -k 'test_navigate'    # Run tests matching 'navigate'"
            echo "  $0 test test_basic_flow.py   # Run specific test file"
            echo "  $0 quick                     # Run quick E2E tests"
            echo "  $0 build                     # Just build the service"
            echo "  $0 start                     # Start service for manual testing"
            echo "  $0 list                      # List all test names"
            echo ""
            echo "Environment Variables:"
            echo "  ENERGY_SERVICE_PORT  Port for the service (default: 50051)"
            echo ""
            echo "Coverage:"
            echo "  Coverage reports are saved to: $COVERAGE_DIR/"
            ;;
        *)
            log_error "Unknown command: $command"
            echo "Run '$0 help' for usage information."
            exit 1
            ;;
    esac
}

# Run main with all arguments
main "$@"
