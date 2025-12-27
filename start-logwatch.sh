#!/bin/bash
# Start logwatch-menubar

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# Kill any existing instance
pkill -f "python.*logwatch-menubar.py" 2>/dev/null

# Start the app
cd "$SCRIPT_DIR"
nohup python3 logwatch-menubar.py > /tmp/logwatch-menubar.out 2>&1 &

echo "logwatch-menubar started"
