#!/bin/bash
# Energy Service Launcher for macOS
# Handles code signing and proper app bundle launch

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

APP_NAME="energy-service"
APP_BUNDLE="${APP_NAME}.app"
PLIST_PATH="${APP_BUNDLE}/Contents/Info.plist"
SERVICE_PORT="50051"
LOG_PATH="/tmp/energy-service.log"

is_port_listening() {
    lsof -nP -iTCP:"${SERVICE_PORT}" -sTCP:LISTEN >/dev/null 2>&1
}

print_failure_diagnostics() {
    echo
    echo "===== Startup diagnostics ====="
    echo "Expected listen port: ${SERVICE_PORT}"
    echo "Working directory: ${SCRIPT_DIR}"

    echo
    echo "Port owner snapshot:"
    if ! lsof -nP -iTCP:"${SERVICE_PORT}" -sTCP:LISTEN; then
        echo "(no listener found on ${SERVICE_PORT})"
    fi

    echo
    echo "Energy-related processes:"
    if ! pgrep -fal "$APP_NAME|energy-server"; then
        echo "(no energy-related process found)"
    fi

    echo
    if [ -f "$LOG_PATH" ]; then
        echo "Recent fallback log (${LOG_PATH}):"
        tail -n 40 "$LOG_PATH" || true
    else
        echo "Fallback log file not found: ${LOG_PATH}"
    fi

    echo
    echo "Suggested next steps:"
    echo "1) Retry guarded startup: bash ${SCRIPT_DIR}/../scripts/ensure_energy_service.sh"
    echo "2) Run health check: uv run python ${SCRIPT_DIR}/../scripts/energy_service_healthcheck.py --host localhost --port ${SERVICE_PORT}"
    echo "3) If launching from terminal, ensure current user session has GUI permissions (Finder/login session)."
    echo "==============================="
}

cleanup_stale_processes() {
    echo "Cleaning stale Energy service processes..."

    local stale_pids
    stale_pids="$(
        {
            pgrep -f "$SCRIPT_DIR/$APP_NAME" || true
            pgrep -f "$SCRIPT_DIR/$APP_BUNDLE/Contents/MacOS/$APP_NAME" || true
            pgrep -f "$SCRIPT_DIR/energy-server" || true
        } | sort -u
    )"

    if [ -n "$stale_pids" ]; then
        echo "$stale_pids" | while IFS= read -r pid; do
            [ -z "$pid" ] && continue
            if [ "$pid" = "$$" ] || [ "$pid" = "$PPID" ]; then
                continue
            fi
            kill "$pid" 2>/dev/null || true
        done

        sleep 1

        echo "$stale_pids" | while IFS= read -r pid; do
            [ -z "$pid" ] && continue
            if kill -0 "$pid" 2>/dev/null; then
                kill -9 "$pid" 2>/dev/null || true
            fi
        done
    fi

    local port_pids
    port_pids="$(lsof -ti "tcp:${SERVICE_PORT}" -sTCP:LISTEN 2>/dev/null | sort -u || true)"
    if [ -n "$port_pids" ]; then
        echo "Cleaning listeners on port ${SERVICE_PORT}: $port_pids"
        echo "$port_pids" | while IFS= read -r pid; do
            [ -z "$pid" ] && continue
            kill "$pid" 2>/dev/null || true
        done
        sleep 1
        echo "$port_pids" | while IFS= read -r pid; do
            [ -z "$pid" ] && continue
            if kill -0 "$pid" 2>/dev/null; then
                kill -9 "$pid" 2>/dev/null || true
            fi
        done
    fi
}

cleanup_stale_processes

# Check if binary exists
if [ ! -f "$APP_NAME" ]; then
    echo "Building $APP_NAME..."
    go build -o "$APP_NAME" .
fi

# Remove old app bundle if symlinks exist
if [ -d "$APP_BUNDLE" ]; then
    echo "Removing old app bundle..."
    rm -rf "$APP_BUNDLE"
fi

# First run to create app bundle (will fail due to code signing)
echo "Creating app bundle..."
./"$APP_NAME" &
FIRST_PID=$!
sleep 2
kill $FIRST_PID 2>/dev/null || true
wait $FIRST_PID 2>/dev/null || true

# Check if app bundle was created
if [ ! -d "$APP_BUNDLE" ]; then
    echo "ERROR: App bundle was not created"
    exit 1
fi

# Inject required privacy usage descriptions to prevent TCC crash on macOS.
# Without NSBluetoothAlwaysUsageDescription, Chromium may abort when touching
# Bluetooth-related APIs during page/runtime initialization.
if [ -f "$PLIST_PATH" ]; then
    /usr/libexec/PlistBuddy -c "Add :NSBluetoothAlwaysUsageDescription string \"Energy service does not use Bluetooth directly; this key prevents macOS runtime crash triggered by embedded Chromium.\"" "$PLIST_PATH" 2>/dev/null || \
    /usr/libexec/PlistBuddy -c "Set :NSBluetoothAlwaysUsageDescription \"Energy service does not use Bluetooth directly; this key prevents macOS runtime crash triggered by embedded Chromium.\"" "$PLIST_PATH"

    # Add legacy key as compatibility fallback on older systems.
    /usr/libexec/PlistBuddy -c "Add :NSBluetoothPeripheralUsageDescription string \"Energy service does not use Bluetooth directly; this key prevents macOS runtime crash triggered by embedded Chromium.\"" "$PLIST_PATH" 2>/dev/null || \
    /usr/libexec/PlistBuddy -c "Set :NSBluetoothPeripheralUsageDescription \"Energy service does not use Bluetooth directly; this key prevents macOS runtime crash triggered by embedded Chromium.\"" "$PLIST_PATH"
fi

# Replace symlinks with actual files in Helper apps
echo "Fixing Helper app symlinks..."
for helper in "$APP_NAME Helper" "$APP_NAME Helper (GPU)" "$APP_NAME Helper (Renderer)" "$APP_NAME Helper (Plugin)"; do
    helper_path="$APP_BUNDLE/Contents/Frameworks/${helper}.app/Contents/MacOS/${helper}"
    if [ -L "$helper_path" ]; then
        rm "$helper_path"
        cp "$APP_NAME" "$helper_path"
    fi
done

# Code sign all components
echo "Code signing app bundle..."
codesign --force --deep --sign - "$APP_BUNDLE/Contents/Frameworks/$APP_NAME Helper.app" 2>/dev/null || true
codesign --force --deep --sign - "$APP_BUNDLE/Contents/Frameworks/$APP_NAME Helper (GPU).app" 2>/dev/null || true
codesign --force --deep --sign - "$APP_BUNDLE/Contents/Frameworks/$APP_NAME Helper (Renderer).app" 2>/dev/null || true
codesign --force --deep --sign - "$APP_BUNDLE/Contents/Frameworks/$APP_NAME Helper (Plugin).app" 2>/dev/null || true
codesign --force --deep --sign - "$APP_BUNDLE" 2>/dev/null || true

echo "Starting $APP_BUNDLE..."
if ! open -n "$APP_BUNDLE"; then
    echo "Warning: 'open' failed (likely no GUI session). Falling back to direct binary launch."
    nohup "$APP_BUNDLE/Contents/MacOS/$APP_NAME" >"$LOG_PATH" 2>&1 &
    echo "Fallback log: $LOG_PATH"
fi

# Wait and check if service is running
startup_ok=0
for _ in $(seq 1 12); do
    if is_port_listening; then
        startup_ok=1
        break
    fi
    sleep 1
done

if [ "$startup_ok" -eq 1 ]; then
    echo "Energy service started successfully on port ${SERVICE_PORT}"
else
    echo "ERROR: Energy service did not start on port ${SERVICE_PORT}"
    print_failure_diagnostics
    exit 1
fi
