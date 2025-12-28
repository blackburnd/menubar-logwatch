#!/bin/bash
# Create a launcher application for auto-start on login

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_DIR="$( cd "$SCRIPT_DIR/.." && pwd )"
LAUNCHER_NAME="Logwatch.app"
LAUNCHER_PATH="$HOME/Applications/$LAUNCHER_NAME"

echo "=== Logwatch Launcher Creator ==="
echo ""

# Create Applications directory if it doesn't exist
mkdir -p "$HOME/Applications"

# Create the .app bundle structure
mkdir -p "$LAUNCHER_PATH/Contents/MacOS"
mkdir -p "$LAUNCHER_PATH/Contents/Resources"

# Create the launcher script
cat > "$LAUNCHER_PATH/Contents/MacOS/launcher" << EOF
#!/bin/bash
"$PROJECT_DIR/bin/start-logwatch.sh"
EOF

chmod +x "$LAUNCHER_PATH/Contents/MacOS/launcher"

# Create Info.plist
cat > "$LAUNCHER_PATH/Contents/Info.plist" << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleExecutable</key>
    <string>launcher</string>
    <key>CFBundleIdentifier</key>
    <string>com.menubar.logwatch</string>
    <key>CFBundleName</key>
    <string>Logwatch</string>
    <key>CFBundleVersion</key>
    <string>1.0</string>
    <key>LSUIElement</key>
    <true/>
</dict>
</plist>
EOF

echo "✓ Launcher app created at: $LAUNCHER_PATH"
echo ""
echo "To enable auto-start on login:"
echo "  1. Open System Settings → General → Login Items"
echo "  2. Click the '+' button under 'Open at Login'"
echo "  3. Navigate to: $LAUNCHER_PATH"
echo "  4. Click 'Open'"
echo ""
echo "The app will now start automatically when you log in!"
