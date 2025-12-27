# menubar-logwatch

A macOS menubar application that monitors log files for pattern matches, playing a sound alert when detected. Built with [rumps](https://github.com/jaredks/rumps).

![Python 3.6+](https://img.shields.io/badge/python-3.6+-blue.svg)
![macOS](https://img.shields.io/badge/platform-macOS-lightgrey.svg)
![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)

## Features

- **Menubar status indicators**: `[PID]` (watching), `[PID]!` (match detected), `[PID]?` (not configured)
- **Multi-directory monitoring** with filesystem scanning
- **Configurable match patterns** with live preview editor
- **Datetime range filtering** for targeted log analysis
- **Multiple editor support**: Console, VS Code, Sublime Text, BBEdit, Emacs, TextMate, Vim
- **Per-file match counting** with matched line tracking
- **View in Finder** and process inspection via `lsof`
- **Persistent state** across restarts (file positions, match counts)
- **Sound alerts** when patterns are matched (toggleable)
- **Auto-start on login** (optional)

## Installation

### Requirements

- macOS 12+
- Python 3.6+

### Quick Start

```bash
# Clone the repository
git clone https://github.com/blackburnd/menubar-logwatch.git
cd menubar-logwatch

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run the application
python logwatch-menubar.py
```

### Dependencies

- **rumps** - macOS menubar framework
- **watchdog** - Filesystem event monitoring
- **pyobjc-framework-Cocoa** - Native macOS UI dialogs

## Usage

### Adding Directories to Watch

1. Click the menubar icon
2. Go to `Directories` > `Add Directory...`
3. Select a directory containing log files

### Scanning for Log Files

1. Click `Scan` > `Scan Directory...`
2. Select a starting path
3. The scanner runs in background showing progress
4. Discovered log files are indexed automatically

### Viewing Indexed Files

1. Click `Indexed Files (N)` to see monitored files
2. Each file shows: `filename.log [match_count]`
3. File options include:
   - **View in Finder** - Reveal file in Finder
   - **Open With** - Open in your preferred editor at specific line
   - **View Matches** - See matched lines with line numbers
   - **Show Processes** - View processes reading/writing the file
   - **Copy Path/File** - Copy to clipboard
   - **Reset Count** - Reset match count for this file

### Managing Match Patterns

1. Go to `Match Patterns (N)`
2. **Add Pattern...** - Opens pattern editor with live preview
3. Each pattern has **Edit** and **Remove** options

Patterns are case-insensitive. Prefix with `^` for regex patterns.

### Editor Configuration

1. Go to `Settings` > `Editors`
2. Each editor can be:
   - **Enabled/Disabled** - Toggle visibility in menus
   - **Located** - Find where the editor is installed
   - **Customized** - Edit the command template
   - **Reset** - Restore default configuration

Command templates use `{file}` and `{line}` placeholders.

### Datetime Filtering

1. Go to `Settings` > `Datetime Filter`
2. Set start and/or end datetime
3. Only log entries within the range will be counted

## Configuration

Configuration is stored at `~/.config/logwatch-menubar/config.json`:

```json
{
  "directories": ["/path/to/logs"],
  "sound_enabled": true,
  "error_patterns": ["exception", "error", "traceback", "failed", "critical"],
  "editors": {
    "vscode": {"enabled": true, "command": "code --goto {file}:{line}"}
  }
}
```

Indexed files are stored at `~/.config/logwatch-menubar/log_index.json`.

## Log File Detection

The scanner identifies log files by:

1. File extension: `.log` or `.logs`
2. Filename containing "log" with timestamp format in content

Recognized timestamp formats:
- ISO: `2024-01-01` or `2024-01-01T12:30:45`
- US: `01-15-2024 12:30:45`
- Bracketed: `[2024-01-01 12:30:45]`
- Time only: `12:30:45`
- Syslog: `Jan 15 12:30`

## Default Match Patterns

- exception
- error
- traceback
- failed
- critical

## Development

```bash
# Install dev dependencies
pip install -r requirements-dev.txt

# Run tests
pytest

# Run with coverage
pytest --cov=. --cov-report=html
```

## Uninstall

```bash
# Stop the launch agent (if configured)
launchctl unload ~/Library/LaunchAgents/menubar.logwatch.plist
rm ~/Library/LaunchAgents/menubar.logwatch.plist

# Remove configuration
rm -rf ~/.config/logwatch-menubar
```

## License

MIT

## Acknowledgments

- [rumps](https://github.com/jaredks/rumps) - Ridiculously Uncomplicated macOS Python Statusbar apps
- [watchdog](https://github.com/gorakhargosh/watchdog) - Python API for monitoring file system events
