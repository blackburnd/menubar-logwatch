# logwatch-menubar

A macOS menubar application that monitors log files for exceptions and errors, playing a sound alert when detected.

## Features

- Menubar shows PID for easy process identification (e.g., `[12345]`)
- Status indicators: `[PID]` (watching), `[PID]!` (error detected), `[PID]?` (not configured)
- Watch multiple directories simultaneously
- Scan filesystem for log files with progress indicator
- Index discovered log files for persistent monitoring
- Per-file exception counter with matched line tracking
- **Open files directly** from the menu
- **View matched lines** with line numbers, click to open at specific line
- Persists file positions and error counts across restarts
- Plays system sound when errors are detected
- Configurable error patterns
- Sound alerts can be toggled on/off
- Auto-starts on login (optional)

## Prerequisites

### System Requirements

- **macOS** (tested on macOS 12+)
- **Python 3.6+**

### Python Dependencies

The only external Python package required is `rumps`:

```bash
pip3 install rumps
```

### Optional Dependencies

For the "open file at line number" feature, one of these editors is recommended:

- **VS Code** (`code` command in PATH) - opens directly at line number
- **Sublime Text** (`subl` command in PATH) - opens directly at line number

Without these, files will open in the default text editor (TextEdit).

### Verify Installation

```bash
# Check Python version
python3 --version  # Should be 3.6+

# Check rumps is installed
python3 -c "import rumps; print('rumps OK')"
```

## Installation

### Quick Setup

```bash
cd ~/Documents/menubar
chmod +x setup-logwatch.sh
./setup-logwatch.sh
```

### Manual Installation

1. Install the rumps library:
   ```bash
   pip3 install rumps
   ```

2. Run the application:
   ```bash
   python3 logwatch-menubar.py
   ```

3. Click the `[PID]?` icon in your menubar to configure directories.

## Usage

### Adding Directories

1. Click the menubar icon
2. Go to `Directories` > `Add Directory...`
3. Select a directory containing log files

### Scanning for Log Files

1. Click the menubar icon
2. Go to `Scan for Logs` > `Scan Directory...`
3. Select a starting path (e.g., `/Users/yourname/projects`)
4. The scanner runs in background, showing progress percentage
5. Discovered log files are indexed and monitored automatically

### Viewing Indexed Files

1. Click the menubar icon
2. Go to `Indexed Files (N)` to see all monitored files
3. Each file shows: `filename.log [error_count]`
4. Click a file to see options:
   - **Open File** - Opens in default application
   - **View Matches (N)** - Shows matched lines with line numbers
   - **Reset Count** - Resets error count for this file
   - **Remove from Index** - Stops monitoring this file

### Opening Matched Lines

1. Navigate to a file's `View Matches` submenu
2. Click any matched line (e.g., `L42: error: connection refused...`)
3. The file opens at that exact line in VS Code, Sublime, or your default editor

### Managing Error Patterns

1. Click the menubar icon
2. Go to `Error Patterns (N)`
3. **Add Pattern...** - Add a new search pattern
4. **Remove: pattern** - Remove an existing pattern

Patterns are case-insensitive. Prefix with `^` for regex patterns.

### Resetting Counters

- `Reset Counter` - Resets all exception counts to zero
- `Clear Recent Errors` - Clears the recent errors list

## Configuration

Configuration is stored at `~/.config/logwatch-menubar/config.json`:

```json
{
  "directories": ["/path/to/logs", "/another/path"],
  "sound_enabled": true,
  "error_patterns": ["exception", "error", "traceback", "failed", "critical"]
}
```

Indexed files with positions and error counts are stored at `~/.config/logwatch-menubar/log_index.json`:

```json
{
  "files": {
    "/path/to/file.log": {
      "position": 12345,
      "mtime": 1703654321.0,
      "error_count": 5
    }
  }
}
```

## Log File Detection

The scanner identifies log files by:

1. File extension: `.log` or `.logs`
2. Filename containing "log" with timestamp format in content

Timestamp formats recognized:
- `2024-01-01` or `2024/01/01`
- `01-01-2024` or `01/01/2024`
- `[2024-01-01`
- `12:30:45`
- `Jan 15 12:30`

## Error Detection

Default patterns monitored (case-insensitive):

- exception
- error
- traceback
- failed
- critical

Custom patterns can be added via the menu.

## Troubleshooting

### "rumps not found" error

```bash
pip3 install rumps
# or if using a virtual environment:
source /path/to/venv/bin/activate
pip install rumps
```

### App doesn't start

Check the error log:
```bash
cat /tmp/logwatch-menubar.err
```

### Files not being monitored

- Ensure the file has a `.log` extension or contains "log" in the name
- Check that the file contains recognizable timestamp formats
- Verify the directory is added or the file is in the index

## Uninstall

```bash
launchctl unload ~/Library/LaunchAgents/menubar.logwatch.plist
rm ~/Library/LaunchAgents/menubar.logwatch.plist
rm ~/logwatch-menubar.py
rm -rf ~/.config/logwatch-menubar
```

## License

MIT
