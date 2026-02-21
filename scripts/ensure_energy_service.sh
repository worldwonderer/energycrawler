#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

HOST="${ENERGY_SERVICE_HOST:-localhost}"
PORT="${ENERGY_SERVICE_PORT:-50051}"
TIMEOUT="${ENERGY_HEALTHCHECK_TIMEOUT:-8}"
MAX_RETRIES="${ENERGY_ENSURE_RETRIES:-3}"
SLEEP_SEC="${ENERGY_ENSURE_SLEEP_SEC:-2}"
UV_CACHE_DIR="${UV_CACHE_DIR:-/tmp/energycrawler-uv-cache}"
START_SCRIPT="${PROJECT_ROOT}/energy-service/start-macos.sh"
HEALTHCHECK_SCRIPT="${PROJECT_ROOT}/scripts/energy_service_healthcheck.py"
LOG_PATH="/tmp/energy-service.log"

usage() {
    cat <<'EOF'
Usage: bash scripts/ensure_energy_service.sh [options]

Options:
  --host <host>          Service host (default: localhost)
  --port <port>          Service port (default: 50051)
  --timeout <sec>        Healthcheck timeout seconds (default: 8)
  --retries <n>          Max healthcheck attempts (default: 3)
  --sleep <sec>          Sleep seconds between retries (default: 2)
  -h, --help             Show this help
EOF
}

while (($# > 0)); do
    case "$1" in
    --host)
        HOST="$2"
        shift 2
        ;;
    --port)
        PORT="$2"
        shift 2
        ;;
    --timeout)
        TIMEOUT="$2"
        shift 2
        ;;
    --retries)
        MAX_RETRIES="$2"
        shift 2
        ;;
    --sleep)
        SLEEP_SEC="$2"
        shift 2
        ;;
    -h | --help)
        usage
        exit 0
        ;;
    *)
        echo "Unknown argument: $1" >&2
        usage
        exit 1
        ;;
    esac
done

if [ ! -f "$HEALTHCHECK_SCRIPT" ]; then
    echo "Healthcheck script not found: $HEALTHCHECK_SCRIPT" >&2
    exit 1
fi

if [ ! -x "$START_SCRIPT" ]; then
    echo "Start script not executable: $START_SCRIPT" >&2
    exit 1
fi

if command -v uv >/dev/null 2>&1; then
    mkdir -p "$UV_CACHE_DIR"
    export UV_CACHE_DIR
    CHECK_CMD=(uv run python "$HEALTHCHECK_SCRIPT")
elif command -v python3 >/dev/null 2>&1; then
    CHECK_CMD=(python3 "$HEALTHCHECK_SCRIPT")
else
    echo "python3 not found and uv not available; cannot run healthcheck" >&2
    exit 1
fi

run_healthcheck() {
    "${CHECK_CMD[@]}" --host "$HOST" --port "$PORT" --timeout "$TIMEOUT"
}

attempt=1
while [ "$attempt" -le "$MAX_RETRIES" ]; do
    echo "[ensure] Healthcheck attempt ${attempt}/${MAX_RETRIES} (${HOST}:${PORT})"
    if run_healthcheck; then
        echo "[ensure] Energy service is healthy."
        exit 0
    fi

    if [ "$attempt" -lt "$MAX_RETRIES" ]; then
        echo "[ensure] Service unhealthy, restarting via ${START_SCRIPT}"
        if ! bash "$START_SCRIPT"; then
            echo "[ensure] Restart command returned non-zero."
        fi
        sleep "$SLEEP_SEC"
    fi

    attempt=$((attempt + 1))
done

echo "[ensure] Energy service still unhealthy after ${MAX_RETRIES} attempts."
echo "[ensure] Diagnostics:"
if ! lsof -nP -iTCP:"${PORT}" -sTCP:LISTEN; then
    echo "(no process listening on ${PORT})"
fi

echo
echo "Processes:"
if ! pgrep -fal "energy-service|energy-server"; then
    echo "(no energy process found)"
fi

echo
if [ -f "$LOG_PATH" ]; then
    echo "Last 60 lines of ${LOG_PATH}:"
    tail -n 60 "$LOG_PATH" || true
else
    echo "No fallback log at ${LOG_PATH}"
fi

echo
echo "Actionable next steps:"
echo "1) Ensure current user has GUI session permissions (Finder/login session)."
echo "2) Run manual startup once: bash energy-service/start-macos.sh"
echo "3) Re-run check with JSON: ${CHECK_CMD[*]} --host ${HOST} --port ${PORT} --timeout ${TIMEOUT} --json"
exit 1
