#!/bin/bash
# Energy Service Launcher for macOS
# Handles code signing and proper app bundle launch

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

APP_NAME="energy-service"
APP_BUNDLE="${APP_NAME}.app"

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
open "$APP_BUNDLE"

# Wait a moment and check if service is running
sleep 3
if lsof -i :50051 > /dev/null 2>&1; then
    echo "Energy service started successfully on port 50051"
else
    echo "Warning: Service may not be running. Check Console.app for crash logs."
fi
