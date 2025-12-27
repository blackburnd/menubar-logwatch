#!/bin/bash

# Setup script for logwatch-menubar app

set -e

echo "=== logwatch-menubar Setup ==="
echo ""

# Get username and home directory
USERNAME=$(whoami)
HOME_DIR="$HOME"

echo "Installing for user: $USERNAME"
echo ""

# 1. Install rumps
echo "Step 1: Installing rumps library..."
pip3 install rumps 2>&1 | tail -5
echo "Done: rumps installed"
echo ""

# 2. Copy script to home directory
echo "Step 2: Installing script..."
cp logwatch-menubar.py "$HOME_DIR/logwatch-menubar.py"
chmod +x "$HOME_DIR/logwatch-menubar.py"
echo "Done: Script installed to $HOME_DIR/logwatch-menubar.py"
echo ""

# 3. Update and install launch agent
echo "Step 3: Setting up auto-launch..."
sed "s|YOUR_USERNAME|$USERNAME|g" menubar.logwatch.plist > /tmp/menubar.logwatch.plist
sed -i '' "s|/Users/$USERNAME|$HOME_DIR|g" /tmp/menubar.logwatch.plist

# Find python3 location
PYTHON3_PATH=$(which python3)
sed -i '' "s|/usr/local/bin/python3|$PYTHON3_PATH|g" /tmp/menubar.logwatch.plist

mkdir -p "$HOME_DIR/Library/LaunchAgents"
cp /tmp/menubar.logwatch.plist "$HOME_DIR/Library/LaunchAgents/"
echo "Done: Launch agent installed"
echo ""

# 4. Load the launch agent
echo "Step 4: Starting the app..."
launchctl unload "$HOME_DIR/Library/LaunchAgents/menubar.logwatch.plist" 2>/dev/null || true
launchctl load "$HOME_DIR/Library/LaunchAgents/menubar.logwatch.plist"
echo "Done: App started"
echo ""

echo "=== Setup Complete ==="
echo ""
echo "The log watcher should now appear in your menu bar as 'LOG'"
echo ""
echo "Click the menubar icon and select 'Set Log Directory...' to configure."
echo ""
echo "To stop the app:"
echo "  launchctl unload ~/Library/LaunchAgents/menubar.logwatch.plist"
echo ""
echo "To start the app manually:"
echo "  python3 ~/logwatch-menubar.py"
echo ""
