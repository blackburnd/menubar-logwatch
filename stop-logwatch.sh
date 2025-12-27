#!/bin/bash
# Stop logwatch-menubar

pkill -f "python.*logwatch-menubar.py" 2>/dev/null

echo "logwatch-menubar stopped"
