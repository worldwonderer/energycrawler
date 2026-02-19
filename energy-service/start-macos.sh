#!/bin/bash
# Energy Service Launcher for macOS
# Handles code signing and proper app bundle launch

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

APP_NAME="energy-service"
APP_BUNDLE="${APP_NAME}.app"
PLIST_PATH="${APP_BUNDLE}/Contents/Info.plist"
SERVICE_PORT="50051"

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
    nohup "$APP_BUNDLE/Contents/MacOS/$APP_NAME" >/tmp/energy-service.log 2>&1 &
fi

# Wait a moment and check if service is running
sleep 3
if lsof -i :"${SERVICE_PORT}" > /dev/null 2>&1; then
    echo "Energy service started successfully on port ${SERVICE_PORT}"
else
    echo "Warning: Service may not be running. Check Console.app for crash logs."
fi
