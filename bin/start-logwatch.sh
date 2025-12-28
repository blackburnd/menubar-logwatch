#!/bin/bash
# Start logwatch-menubar

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_DIR="$( cd "$SCRIPT_DIR/.." && pwd )"

# Kill any existing instance
pkill -9 -f "logwatch-menubar.py" 2>/dev/null
sleep 1

# Start the app using the virtual environment
cd "$PROJECT_DIR"
nohup "$PROJECT_DIR/venv/bin/python" logwatch-menubar.py > /tmp/logwatch-menubar.out 2>&1 &

echo "logwatch-menubar started (PID: $!)"
