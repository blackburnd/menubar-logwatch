#!/bin/bash

# Setup script for logwatch-menubar app

set -e

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_DIR="$( cd "$SCRIPT_DIR/.." && pwd )"
PLIST_NAME="com.logwatch.menubar.plist"
LAUNCH_AGENTS_DIR="$HOME/Library/LaunchAgents"

echo "=== logwatch-menubar Setup ==="
echo ""
echo "Project directory: $PROJECT_DIR"
echo ""

# 1. Create virtual environment if it doesn't exist
if [ ! -d "$PROJECT_DIR/venv" ]; then
    echo "Step 1: Creating virtual environment..."
    python3 -m venv "$PROJECT_DIR/venv"
    echo "Done"
else
    echo "Step 1: Virtual environment already exists"
fi
echo ""

# 2. Install dependencies
echo "Step 2: Installing dependencies..."
"$PROJECT_DIR/venv/bin/pip" install -q rumps watchdog pyobjc-framework-Cocoa
echo "Done"
echo ""

# 3. Generate plist with correct paths
echo "Step 3: Generating LaunchAgent plist..."
PYTHON_PATH="$PROJECT_DIR/venv/bin/python"
SCRIPT_PATH="$PROJECT_DIR/logwatch-menubar.py"

cat > "$PROJECT_DIR/$PLIST_NAME" << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.logwatch.menubar</string>
    <key>ProgramArguments</key>
    <array>
        <string>$PYTHON_PATH</string>
        <string>$SCRIPT_PATH</string>
    </array>
    <key>WorkingDirectory</key>
    <string>$PROJECT_DIR</string>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <false/>
    <key>StandardOutPath</key>
    <string>/tmp/logwatch-menubar.out</string>
    <key>StandardErrorPath</key>
    <string>/tmp/logwatch-menubar.err</string>
</dict>
</plist>
EOF
echo "Done"
echo ""

# 4. Install LaunchAgent
echo "Step 4: Installing LaunchAgent..."
mkdir -p "$LAUNCH_AGENTS_DIR"

# Unload if already loaded
launchctl unload "$LAUNCH_AGENTS_DIR/$PLIST_NAME" 2>/dev/null || true

# Copy plist to LaunchAgents
cp "$PROJECT_DIR/$PLIST_NAME" "$LAUNCH_AGENTS_DIR/"
echo "Done: Installed to $LAUNCH_AGENTS_DIR/$PLIST_NAME"
echo ""

# 5. Load the LaunchAgent
echo "Step 5: Loading LaunchAgent..."
launchctl load "$LAUNCH_AGENTS_DIR/$PLIST_NAME"
echo "Done"
echo ""

echo "=== Setup Complete ==="
echo ""
echo "The log watcher should now appear in your menu bar."
echo "It will start automatically on login."
echo ""
echo "To manage the service:"
echo "  Start:  $SCRIPT_DIR/start-logwatch.sh"
echo "  Stop:   $SCRIPT_DIR/stop-logwatch.sh"
echo ""
echo "To disable auto-start:"
echo "  launchctl unload ~/Library/LaunchAgents/$PLIST_NAME"
echo ""
