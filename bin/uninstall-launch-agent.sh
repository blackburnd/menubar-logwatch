#!/bin/bash
# Uninstall LaunchAgent for auto-start

PLIST_NAME="com.menubar.logwatch.plist"
PLIST_PATH="$HOME/Library/LaunchAgents/$PLIST_NAME"

echo "=== Logwatch LaunchAgent Uninstaller ==="
echo ""

if [ ! -f "$PLIST_PATH" ]; then
    echo "LaunchAgent not found. Nothing to uninstall."
    exit 0
fi

# Unload the launch agent
launchctl unload "$PLIST_PATH" 2>/dev/null

# Remove the plist file
rm "$PLIST_PATH"

echo "✓ LaunchAgent removed"
echo "✓ Auto-start on login disabled"
echo ""
echo "The app is still running. To stop it:"
echo "  ./bin/stop-logwatch.sh"
