#!/bin/bash
# Install LaunchAgent for auto-start on login

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_DIR="$( cd "$SCRIPT_DIR/.." && pwd )"
PLIST_NAME="com.menubar.logwatch.plist"
PLIST_PATH="$HOME/Library/LaunchAgents/$PLIST_NAME"

echo "=== Logwatch LaunchAgent Installer ==="
echo ""

# Create LaunchAgents directory if it doesn't exist
mkdir -p "$HOME/Library/LaunchAgents"

# Create the plist file
cat > "$PLIST_PATH" << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.menubar.logwatch</string>
    <key>ProgramArguments</key>
    <array>
        <string>$PROJECT_DIR/bin/start-logwatch.sh</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <false/>
    <key>StandardErrorPath</key>
    <string>/tmp/logwatch-menubar.err</string>
    <key>StandardOutPath</key>
    <string>/tmp/logwatch-menubar.out</string>
</dict>
</plist>
EOF

echo " LaunchAgent installed at: $PLIST_PATH"
echo ""

# Stop any existing instance
./bin/stop-logwatch.sh 2>/dev/null

# Load the launch agent
launchctl load "$PLIST_PATH"

echo " LaunchAgent loaded and will start automatically on login"
echo ""
echo "The app is now running and will auto-start when you log in."
echo ""
echo "To uninstall auto-start:"
echo "  ./bin/uninstall-launch-agent.sh"
"$PROJECT_DIR/bin/start-logwatch.sh" 2>/dev/null || true
"$PROJECT_DIR/../menubar-daysfrom/bin/start-daysfrom.sh" 2>/dev/null || true
