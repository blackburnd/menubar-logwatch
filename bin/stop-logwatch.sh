#!/bin/bash
# Stop logwatch-menubar

pkill -9 -f "logwatch-menubar.py" 2>/dev/null

echo "logwatch-menubar stopped"
