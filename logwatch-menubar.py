#!/usr/bin/env python3
"""
logwatch-menubar - A macOS menubar app that monitors log files for pattern matches.

Watches configured log directories for match patterns and plays a sound alert
when matches are detected. Displays recent matches in the menubar dropdown.
"""

import os
import re
import json
import threading
import subprocess
from pathlib import Path
from datetime import datetime, timedelta
from collections import deque

import rumps
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler, FileModifiedEvent
from AppKit import (
    NSApp, NSAlert, NSDatePicker, NSDatePickerStyleClockAndCalendar,
    NSDatePickerStyleTextFieldAndStepper,
    NSDatePickerElementFlagYearMonthDay, NSDatePickerElementFlagHourMinuteSecond,
    NSModalResponseOK, NSView, NSMakeRect, NSTextField, NSFont,
    NSStackView, NSUserInterfaceLayoutOrientationVertical,
    NSObject, NSScrollView, NSTableView, NSTableColumn,
    NSBezelBorder, NSTableViewSelectionHighlightStyleRegular,
    NSMenu, NSColor, NSTextView, NSAttributedString, NSFontAttributeName,
    NSForegroundColorAttributeName, NSBackgroundColorAttributeName,
    NSMutableAttributedString, NSPopUpButton
)
from PyObjCTools import AppHelper
import objc
from Foundation import NSDate, NSCalendar, NSCalendarUnitYear, NSCalendarUnitMonth, NSCalendarUnitDay, NSCalendarUnitHour, NSCalendarUnitMinute, NSCalendarUnitSecond


CONFIG_PATH = Path.home() / ".config" / "logwatch-menubar" / "config.json"
INDEX_PATH = Path.home() / ".config" / "logwatch-menubar" / "log_index.json"
DEFAULT_SOUND = "/System/Library/Sounds/Basso.aiff"
MAX_RECENT_ERRORS = 10
SCRIPT_DIR = Path(__file__).parent.resolve()
ICON_PATH = SCRIPT_DIR / "log_icon.png"

# Default patterns to match in log files
DEFAULT_ERROR_PATTERNS = [
    "exception",
    "error",
    "traceback",
    "failed",
    "critical",
]

# Default editor configurations: {editor_id: {name, command_template, enabled}}
# command_template uses {file} and {line} placeholders
DEFAULT_EDITORS = {
    "console": {
        "name": "Console",
        "command": "open -a Console {file}",
        "enabled": True,
        "supports_line": False,
    },
    "vscode": {
        "name": "VS Code",
        "command": "code --goto {file}:{line}",
        "enabled": True,
        "supports_line": True,
    },
    "sublime": {
        "name": "Sublime Text",
        "command": "subl {file}:{line}",
        "enabled": True,
        "supports_line": True,
    },
    "bbedit": {
        "name": "BBEdit",
        "command": "bbedit +{line} {file}",
        "enabled": True,
        "supports_line": True,
    },
    "emacs": {
        "name": "Emacs",
        "command": "emacsclient -n +{line} {file}",
        "enabled": True,
        "supports_line": True,
    },
    "textmate": {
        "name": "TextMate",
        "command": "mate -l {line} {file}",
        "enabled": True,
        "supports_line": True,
    },
    "vim": {
        "name": "Vim (Terminal)",
        "command": "vim +{line} {file}",
        "enabled": True,
        "supports_line": True,
        "use_terminal": True,
    },
}

# Pattern to detect log file format (timestamp at start of line)
LOG_LINE_PATTERN = re.compile(
    r"^\d{4}[-/]\d{2}[-/]\d{2}|"  # 2024-01-01 or 2024/01/01
    r"^\d{2}[-/]\d{2}[-/]\d{4}|"  # 01-01-2024 or 01/01/2024
    r"^\[\d{4}[-/]\d{2}[-/]\d{2}|"  # [2024-01-01
    r"^\d{2}:\d{2}:\d{2}|"  # 12:30:45
    r"^\w{3}\s+\d{1,2}\s+\d{2}:\d{2}"  # Jan 15 12:30
)

# Patterns for extracting timestamps from log lines
TIMESTAMP_PATTERNS = [
    # ISO format: 2024-01-15 12:30:45 or 2024-01-15T12:30:45
    (re.compile(r"(\d{4})[-/](\d{2})[-/](\d{2})[T\s](\d{2}):(\d{2}):(\d{2})"),
     lambda m: datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)),
                        int(m.group(4)), int(m.group(5)), int(m.group(6)))),
    # ISO format date only: 2024-01-15
    (re.compile(r"(\d{4})[-/](\d{2})[-/](\d{2})"),
     lambda m: datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)))),
    # US format: 01-15-2024 12:30:45
    (re.compile(r"(\d{2})[-/](\d{2})[-/](\d{4})\s+(\d{2}):(\d{2}):(\d{2})"),
     lambda m: datetime(int(m.group(3)), int(m.group(1)), int(m.group(2)),
                        int(m.group(4)), int(m.group(5)), int(m.group(6)))),
    # Bracketed ISO: [2024-01-15 12:30:45]
    (re.compile(r"\[(\d{4})[-/](\d{2})[-/](\d{2})[T\s](\d{2}):(\d{2}):(\d{2})"),
     lambda m: datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)),
                        int(m.group(4)), int(m.group(5)), int(m.group(6)))),
]

# Format for storing datetime in config
DATETIME_FORMAT = "%Y-%m-%d %H:%M:%S"


def parse_log_timestamp(line):
    """Extract timestamp from a log line. Returns datetime or None."""
    for pattern, converter in TIMESTAMP_PATTERNS:
        match = pattern.search(line)
        if match:
            try:
                return converter(match)
            except (ValueError, IndexError):
                continue
    return None


def datetime_to_nsdate(dt):
    """Convert Python datetime to NSDate."""
    if dt is None:
        return NSDate.date()
    calendar = NSCalendar.currentCalendar()
    components = calendar.components_fromDate_(
        NSCalendarUnitYear | NSCalendarUnitMonth | NSCalendarUnitDay |
        NSCalendarUnitHour | NSCalendarUnitMinute | NSCalendarUnitSecond,
        NSDate.date()
    )
    components.setYear_(dt.year)
    components.setMonth_(dt.month)
    components.setDay_(dt.day)
    components.setHour_(dt.hour)
    components.setMinute_(dt.minute)
    components.setSecond_(dt.second)
    return calendar.dateFromComponents_(components)


def nsdate_to_datetime(nsdate):
    """Convert NSDate to Python datetime."""
    calendar = NSCalendar.currentCalendar()
    components = calendar.components_fromDate_(
        NSCalendarUnitYear | NSCalendarUnitMonth | NSCalendarUnitDay |
        NSCalendarUnitHour | NSCalendarUnitMinute | NSCalendarUnitSecond,
        nsdate
    )
    return datetime(
        year=components.year(),
        month=components.month(),
        day=components.day(),
        hour=components.hour(),
        minute=components.minute(),
        second=components.second()
    )


def show_datetime_picker(title, message, initial_datetime=None):
    """Show a native macOS date/time picker dialog with graphical calendar.

    Returns:
        datetime if OK clicked
        None if Cancel clicked
        'clear' if Clear clicked
    """
    # Bring app to front so dialog appears above other windows
    NSApp.activateIgnoringOtherApps_(True)

    alert = NSAlert.alloc().init()
    alert.setMessageText_(title)
    alert.setInformativeText_(message)
    alert.addButtonWithTitle_("OK")
    alert.addButtonWithTitle_("Clear")
    alert.addButtonWithTitle_("Cancel")

    # Create container view for the calendar and time picker
    container = NSView.alloc().initWithFrame_(NSMakeRect(0, 0, 280, 230))

    # Create graphical calendar picker for date (larger, shows month grid)
    calendar_picker = NSDatePicker.alloc().initWithFrame_(NSMakeRect(0, 40, 280, 190))
    calendar_picker.setDatePickerStyle_(NSDatePickerStyleClockAndCalendar)
    calendar_picker.setDatePickerElements_(NSDatePickerElementFlagYearMonthDay)
    calendar_picker.setBezeled_(False)
    calendar_picker.setDrawsBackground_(False)

    # Create text field stepper for time (compact, below calendar)
    time_picker = NSDatePicker.alloc().initWithFrame_(NSMakeRect(70, 5, 140, 28))
    time_picker.setDatePickerStyle_(NSDatePickerStyleTextFieldAndStepper)
    time_picker.setDatePickerElements_(NSDatePickerElementFlagHourMinuteSecond)

    # Set initial date/time
    initial_nsdate = datetime_to_nsdate(initial_datetime) if initial_datetime else NSDate.date()
    calendar_picker.setDateValue_(initial_nsdate)
    time_picker.setDateValue_(initial_nsdate)

    # Add subviews
    container.addSubview_(calendar_picker)
    container.addSubview_(time_picker)

    alert.setAccessoryView_(container)

    # Make the alert window float above all others
    alert.window().setLevel_(3)  # NSFloatingWindowLevel

    # Run the dialog
    # Button responses: OK=1000, Clear=1001, Cancel=1002
    response = alert.runModal()

    if response == 1000:  # OK
        # Combine date from calendar and time from time picker
        cal_date = nsdate_to_datetime(calendar_picker.dateValue())
        time_date = nsdate_to_datetime(time_picker.dateValue())
        combined = datetime(
            cal_date.year, cal_date.month, cal_date.day,
            time_date.hour, time_date.minute, time_date.second
        )
        return combined
    elif response == 1001:  # Clear
        return 'clear'
    return None  # Cancel


# Sample log lines for pattern testing (Lorem ipsum split into 5 parts)
SAMPLE_LOG_LINES = [
    "2024-01-15 10:00:01 INFO Lorem ipsum dolor sit amet consectetur adipiscing elit",
    "2024-01-15 10:00:02 ERROR Sed do eiusmod tempor incididunt ut labore et dolore",
    "2024-01-15 10:00:03 WARN Ut enim ad minim veniam quis nostrud exercitation",
    "2024-01-15 10:00:04 DEBUG Duis aute irure dolor in reprehenderit in voluptate",
    "2024-01-15 10:00:05 CRITICAL Excepteur sint occaecat cupidatat non proident sunt",
]

# Common regex patterns for tooltip help
REGEX_HELP = """Common patterns:
  error|warn     - Match 'error' OR 'warn'
  ^ERROR         - Line starts with ERROR (regex)
  ^\\[ERROR\\]   - Match literal [ERROR]
  failed.*conn   - 'failed' followed by 'conn'
  \\d+           - One or more digits"""


def show_pattern_editor(title, initial_pattern="", indexed_files=None):
    """Show pattern editor with live preview against sample log lines.

    Args:
        title: Dialog title
        initial_pattern: Pre-filled pattern text
        indexed_files: Optional dict of {filepath: {...}} for file selection

    Returns the pattern string or None if cancelled.
    """
    NSApp.activateIgnoringOtherApps_(True)

    alert = NSAlert.alloc().init()
    alert.setMessageText_(title)
    alert.setInformativeText_("Enter pattern (case-insensitive, ^ prefix for regex):")
    alert.addButtonWithTitle_("OK")
    alert.addButtonWithTitle_("Cancel")

    # Create container view (taller to accommodate file selector)
    container = NSView.alloc().initWithFrame_(NSMakeRect(0, 0, 450, 220))

    # Pattern input field (single line)
    pattern_field = NSTextField.alloc().initWithFrame_(NSMakeRect(0, 190, 450, 24))
    pattern_field.setStringValue_(initial_pattern if initial_pattern else "")
    pattern_field.setFont_(NSFont.systemFontOfSize_(12))
    pattern_field.setPlaceholderString_("e.g., error, ^WARN.*, failed")
    container.addSubview_(pattern_field)

    # File selector row
    file_label = NSTextField.alloc().initWithFrame_(NSMakeRect(0, 162, 80, 20))
    file_label.setStringValue_("Test with:")
    file_label.setBezeled_(False)
    file_label.setDrawsBackground_(False)
    file_label.setEditable_(False)
    file_label.setSelectable_(False)
    file_label.setFont_(NSFont.systemFontOfSize_(11))
    container.addSubview_(file_label)

    # File selector popup
    file_popup = NSPopUpButton.alloc().initWithFrame_(NSMakeRect(80, 160, 370, 24))
    file_popup.addItemWithTitle_("Sample lines (Lorem ipsum)")

    # Build list of indexed files
    file_paths = []
    if indexed_files:
        for filepath in sorted(indexed_files.keys()):
            filename = Path(filepath).name
            file_popup.addItemWithTitle_(filename)
            file_paths.append(filepath)

    container.addSubview_(file_popup)

    # Preview label
    preview_label = NSTextField.alloc().initWithFrame_(NSMakeRect(0, 135, 450, 18))
    preview_label.setStringValue_("Preview (matching lines highlighted):")
    preview_label.setBezeled_(False)
    preview_label.setDrawsBackground_(False)
    preview_label.setEditable_(False)
    preview_label.setSelectable_(False)
    preview_label.setFont_(NSFont.systemFontOfSize_(10))
    container.addSubview_(preview_label)

    # Sample lines display (small font, read-only)
    sample_view = NSTextView.alloc().initWithFrame_(NSMakeRect(0, 0, 450, 130))
    sample_view.setFont_(NSFont.userFixedPitchFontOfSize_(9))
    sample_view.setEditable_(False)
    sample_view.setSelectable_(True)
    sample_view.setBackgroundColor_(NSColor.textBackgroundColor())

    container.addSubview_(sample_view)

    alert.setAccessoryView_(container)
    alert.window().setLevel_(3)  # Float above others

    # Store references and current sample lines for the update function
    state = {
        'pattern_field': pattern_field,
        'sample_view': sample_view,
        'file_popup': file_popup,
        'file_paths': file_paths,
        'current_lines': SAMPLE_LOG_LINES[:],
        'last_file_index': 0
    }

    def load_file_lines(filepath, max_lines=20):
        """Load sample lines from a file."""
        lines = []
        try:
            with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                for i, line in enumerate(f):
                    if i >= max_lines:
                        break
                    stripped = line.rstrip("\n\r")
                    if stripped:  # Skip empty lines
                        lines.append(stripped[:100])  # Truncate long lines
        except Exception:
            lines = ["(Could not read file)"]
        return lines if lines else ["(File is empty)"]

    def update_preview():
        """Update the preview with highlighted matches."""
        # Check if file selection changed
        current_file_index = state['file_popup'].indexOfSelectedItem()
        if current_file_index != state['last_file_index']:
            state['last_file_index'] = current_file_index
            if current_file_index == 0:
                # Sample lines
                state['current_lines'] = SAMPLE_LOG_LINES[:]
            else:
                # Load from indexed file
                filepath = state['file_paths'][current_file_index - 1]
                state['current_lines'] = load_file_lines(filepath)

        pattern_text = state['pattern_field'].stringValue().strip()
        current_lines = state['current_lines']

        # Create attributed string for the sample view
        attr_string = NSMutableAttributedString.alloc().initWithString_("")

        small_font = NSFont.userFixedPitchFontOfSize_(9)
        normal_attrs = {
            NSFontAttributeName: small_font,
            NSForegroundColorAttributeName: NSColor.textColor()
        }
        match_attrs = {
            NSFontAttributeName: small_font,
            NSForegroundColorAttributeName: NSColor.whiteColor(),
            NSBackgroundColorAttributeName: NSColor.systemRedColor()
        }

        if pattern_text:
            try:
                # Compile pattern like MultiLogWatcher does
                if pattern_text.startswith("^"):
                    regex = re.compile(pattern_text, re.IGNORECASE)
                else:
                    regex = re.compile(re.escape(pattern_text), re.IGNORECASE)

                for i, line in enumerate(current_lines):
                    if i > 0:
                        attr_string.appendAttributedString_(
                            NSAttributedString.alloc().initWithString_attributes_("\n", normal_attrs)
                        )

                    # Check if line matches
                    if regex.search(line):
                        attr_string.appendAttributedString_(
                            NSAttributedString.alloc().initWithString_attributes_(line, match_attrs)
                        )
                    else:
                        attr_string.appendAttributedString_(
                            NSAttributedString.alloc().initWithString_attributes_(line, normal_attrs)
                        )
            except re.error:
                # Invalid regex - show all lines normally
                for i, line in enumerate(current_lines):
                    if i > 0:
                        attr_string.appendAttributedString_(
                            NSAttributedString.alloc().initWithString_attributes_("\n", normal_attrs)
                        )
                    attr_string.appendAttributedString_(
                        NSAttributedString.alloc().initWithString_attributes_(line, normal_attrs)
                    )
        else:
            # No pattern - show all lines normally
            for i, line in enumerate(current_lines):
                if i > 0:
                    attr_string.appendAttributedString_(
                        NSAttributedString.alloc().initWithString_attributes_("\n", normal_attrs)
                    )
                attr_string.appendAttributedString_(
                    NSAttributedString.alloc().initWithString_attributes_(line, normal_attrs)
                )

        state['sample_view'].textStorage().setAttributedString_(attr_string)

    # Set up timer to update preview periodically while dialog is open
    import threading
    stop_timer = threading.Event()

    def timer_loop():
        last_pattern = ""
        last_file_idx = 0
        while not stop_timer.is_set():
            try:
                current_pattern = state['pattern_field'].stringValue()
                current_file_idx = state['file_popup'].indexOfSelectedItem()
                if current_pattern != last_pattern or current_file_idx != last_file_idx:
                    last_pattern = current_pattern
                    last_file_idx = current_file_idx
                    AppHelper.callAfter(update_preview)
            except Exception:
                pass
            stop_timer.wait(0.2)

    timer_thread = threading.Thread(target=timer_loop, daemon=True)
    timer_thread.start()

    # Initial preview update
    update_preview()

    # Add tooltip with regex help
    pattern_field.setToolTip_(REGEX_HELP)

    # Run dialog
    response = alert.runModal()

    # Stop the timer
    stop_timer.set()

    if response == 1000:  # OK
        return pattern_field.stringValue().strip()
    return None


class LogScanner:
    """Scans filesystem for log files in background."""

    def __init__(self, callback_found, callback_done, callback_progress):
        self.callback_found = callback_found
        self.callback_done = callback_done
        self.callback_progress = callback_progress
        self.running = False
        self.thread = None
        self.scan_path = None
        self.found_count = 0
        self.total_dirs = 0
        self.scanned_dirs = 0

    def start_scan(self, start_path):
        """Start scanning from the given path."""
        if self.running:
            return
        self.scan_path = Path(start_path)
        self.running = True
        self.found_count = 0
        self.total_dirs = 0
        self.scanned_dirs = 0
        self.thread = threading.Thread(target=self._scan_loop, daemon=True)
        self.thread.start()

    def stop(self):
        """Stop scanning."""
        self.running = False
        if self.thread:
            self.thread.join(timeout=2)

    def _count_directories(self, directory, depth=0):
        """Count directories for progress estimation."""
        if depth > 3 or not self.running:
            return 0
        count = 1
        try:
            for entry in os.scandir(directory):
                if not self.running:
                    return count
                try:
                    if entry.is_dir(follow_symlinks=False):
                        if entry.name.startswith("."):
                            continue
                        if entry.name in ("node_modules", "__pycache__", "venv", ".git"):
                            continue
                        count += self._count_directories(entry.path, depth + 1)
                except (PermissionError, OSError):
                    pass
        except (PermissionError, OSError):
            pass
        return count

    def _scan_loop(self):
        """Main scan loop."""
        try:
            # First pass: estimate total directories (limited depth)
            self.total_dirs = self._count_directories(self.scan_path)
            self.callback_progress(0.0)
            # Second pass: actual scan
            self._scan_directory(self.scan_path)
        except Exception:
            pass
        finally:
            self.running = False
            self.callback_done(self.found_count)

    def _scan_directory(self, directory):
        """Recursively scan a directory for log files."""
        if not self.running:
            return

        self.scanned_dirs += 1
        if self.total_dirs > 0:
            progress = min(self.scanned_dirs / self.total_dirs, 0.99)
            self.callback_progress(progress)

        try:
            for entry in os.scandir(directory):
                if not self.running:
                    return

                try:
                    if entry.is_dir(follow_symlinks=False):
                        # Skip hidden directories and common non-log locations
                        if entry.name.startswith("."):
                            continue
                        if entry.name in ("node_modules", "__pycache__", "venv", ".git"):
                            continue
                        self._scan_directory(entry.path)
                    elif entry.is_file(follow_symlinks=False):
                        if self._is_log_file(entry.path):
                            self.found_count += 1
                            self.callback_found(entry.path)
                except PermissionError:
                    pass
                except Exception:
                    pass
        except PermissionError:
            pass
        except Exception:
            pass

    def _is_log_file(self, filepath):
        """Check if a file appears to be a log file."""
        path = Path(filepath)

        # Check extension
        if path.suffix.lower() in (".log", ".logs"):
            return True

        # Check if name contains 'log'
        if "log" in path.name.lower():
            # Verify it looks like a text log by checking first few lines
            return self._has_log_format(filepath)

        return False

    def _has_log_format(self, filepath):
        """Check if file has typical log format (timestamp per line)."""
        try:
            with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                # Check first 5 non-empty lines
                lines_checked = 0
                matches = 0
                for line in f:
                    if lines_checked >= 5:
                        break
                    line = line.strip()
                    if not line:
                        continue
                    lines_checked += 1
                    if LOG_LINE_PATTERN.match(line):
                        matches += 1

                # If at least 2 of 5 lines look like log entries
                return matches >= 2
        except Exception:
            return False


MAX_MATCHED_LINES_PER_FILE = 50


class LogFileEventHandler(FileSystemEventHandler):
    """Handles file system events for log files."""

    def __init__(self, watcher):
        super().__init__()
        self.watcher = watcher

    def on_modified(self, event):
        """Called when a file is modified."""
        if event.is_directory:
            return
        filepath = event.src_path
        # Check if this is a watched file or in a watched directory
        if self.watcher._should_watch_file(filepath):
            self.watcher._check_file_immediate(filepath)

    def on_created(self, event):
        """Called when a new file is created."""
        if event.is_directory:
            return
        filepath = event.src_path
        # Check if this is a log file in a watched directory
        if filepath.endswith('.log') and self.watcher._should_watch_file(filepath):
            self.watcher._check_file_immediate(filepath)


class MultiLogWatcher:
    """Watches multiple log directories and indexed files for errors using FSEvents."""

    def __init__(self, callback, error_patterns=None):
        self.callback = callback
        self.file_positions = {}
        self.file_error_counts = {}
        self.file_matched_lines = {}  # {filepath: deque of (line_num, line_text, timestamp)}
        self.running = False
        self.observer = None
        self.watch_dirs = set()
        self.watch_files = set()
        self.watched_paths = set()  # Paths currently being observed
        self.lock = threading.Lock()
        self.start_datetime = None  # Filter: only count matches after this time
        self.end_datetime = None    # Filter: only count matches before this time
        self.set_error_patterns(error_patterns or DEFAULT_ERROR_PATTERNS)

    def set_datetime_filter(self, start_dt=None, end_dt=None):
        """Set datetime range filter for matching lines."""
        self.start_datetime = start_dt
        self.end_datetime = end_dt

    def set_error_patterns(self, patterns):
        """Set the error patterns to match against."""
        self.error_patterns = [
            re.compile(re.escape(p) if not p.startswith("^") else p, re.IGNORECASE)
            for p in patterns
        ]

    def set_directories(self, directories):
        """Set directories to watch."""
        with self.lock:
            self.watch_dirs = set(directories)

    def set_indexed_files(self, files):
        """Set indexed files to watch."""
        with self.lock:
            self.watch_files = set(files)

    def add_indexed_file(self, filepath):
        """Add a single indexed file."""
        with self.lock:
            self.watch_files.add(filepath)
        # Update FSEvents watches to include new file's directory
        self._update_watches()

    def get_error_count(self, filepath):
        """Get error count for a specific file."""
        return self.file_error_counts.get(filepath, 0)

    def get_total_error_count(self):
        """Get total error count across all files."""
        return sum(self.file_error_counts.values())

    def reset_counts(self):
        """Reset all error counts and matched lines."""
        self.file_error_counts.clear()
        self.file_matched_lines.clear()

    def reset_file_count(self, filepath):
        """Reset error count and matched lines for a specific file."""
        if filepath in self.file_error_counts:
            self.file_error_counts[filepath] = 0
        if filepath in self.file_matched_lines:
            self.file_matched_lines[filepath].clear()

    def get_matched_lines(self, filepath):
        """Get matched lines for a specific file."""
        return list(self.file_matched_lines.get(filepath, []))

    def _add_matched_line(self, filepath, line_num, line_text, line_timestamp=None):
        """Add a matched line for a file."""
        if filepath not in self.file_matched_lines:
            self.file_matched_lines[filepath] = deque(maxlen=MAX_MATCHED_LINES_PER_FILE)
        self.file_matched_lines[filepath].append((line_num, line_text.strip(), line_timestamp))

    def _is_in_datetime_range(self, line_timestamp):
        """Check if a timestamp is within the configured datetime range."""
        if line_timestamp is None:
            # If no timestamp could be parsed, include it by default
            return True
        if self.start_datetime and line_timestamp < self.start_datetime:
            return False
        if self.end_datetime and line_timestamp > self.end_datetime:
            return False
        return True

    def get_file_state(self):
        """Export current file positions and error counts for persistence."""
        state = {}
        for filepath in set(self.file_positions.keys()) | set(self.file_error_counts.keys()):
            pos, mtime = self.file_positions.get(filepath, (0, 0))
            state[filepath] = {
                "position": pos,
                "mtime": mtime,
                "error_count": self.file_error_counts.get(filepath, 0)
            }
        return state

    def restore_file_state(self, state):
        """Restore file positions and error counts from saved state."""
        for filepath, data in state.items():
            self.file_positions[filepath] = (data.get("position", 0), data.get("mtime", 0))
            self.file_error_counts[filepath] = data.get("error_count", 0)

    def reindex_from_positions(self, callback_progress=None):
        """Index files from their saved positions, catching up on new content."""
        files_to_check = set()

        with self.lock:
            for dir_path in self.watch_dirs:
                dir_obj = Path(dir_path)
                if dir_obj.exists():
                    for log_file in dir_obj.glob("*.log"):
                        files_to_check.add(str(log_file))
            files_to_check.update(self.watch_files)

        total_files = len(files_to_check)
        for idx, filepath in enumerate(files_to_check):
            if callback_progress and total_files > 0:
                callback_progress((idx + 1) / total_files)
            try:
                self._index_file_from_position(filepath)
            except Exception:
                pass

    def _index_file_from_position(self, filepath):
        """Index a file from its saved position, or from beginning if new/modified."""
        path = Path(filepath)
        if not path.exists():
            return

        file_key = str(filepath)
        try:
            current_size = path.stat().st_size
            current_mtime = path.stat().st_mtime
        except Exception:
            return

        saved_pos, saved_mtime = self.file_positions.get(file_key, (0, 0))

        # If file was truncated or modified time changed significantly, start from beginning
        if current_size < saved_pos or (saved_mtime > 0 and current_mtime != saved_mtime):
            saved_pos = 0
            self.file_error_counts[file_key] = 0

        # Always clear and rebuild matched lines from the entire file
        if file_key in self.file_matched_lines:
            self.file_matched_lines[file_key].clear()

        # Read entire file to collect matched lines
        total_count = 0
        try:
            with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                line_num = 1
                for line in f:
                    match_count = self._count_matches(line)
                    if match_count > 0:
                        line_timestamp = parse_log_timestamp(line)
                        if self._is_in_datetime_range(line_timestamp):
                            total_count += match_count
                            self._add_matched_line(file_key, line_num, line, line_timestamp)
                    line_num += 1
        except Exception:
            return

        self.file_error_counts[file_key] = total_count
        self.file_positions[file_key] = (current_size, current_mtime)

    def reindex_all_files(self, callback_progress=None, callback_error_found=None):
        """Re-scan all files from beginning to count existing pattern matches."""
        files_to_check = set()

        with self.lock:
            # Get files from directories
            for dir_path in self.watch_dirs:
                dir_obj = Path(dir_path)
                if dir_obj.exists():
                    for log_file in dir_obj.glob("*.log"):
                        files_to_check.add(str(log_file))
            # Add indexed files
            files_to_check.update(self.watch_files)

        # Reset all counts
        self.file_error_counts.clear()
        self.file_positions.clear()

        total_files = len(files_to_check)
        for idx, filepath in enumerate(files_to_check):
            if callback_progress and total_files > 0:
                callback_progress((idx + 1) / total_files)
            try:
                self._count_errors_in_file(filepath, callback_error_found=callback_error_found)
            except Exception:
                pass

    def _count_errors_in_file(self, filepath, callback_error_found=None):
        """Count all error matches in a file from the beginning."""
        path = Path(filepath)
        if not path.exists():
            return

        file_key = str(filepath)
        try:
            current_size = path.stat().st_size
            current_mtime = path.stat().st_mtime
        except Exception:
            return

        # Clear and rebuild matched lines
        if file_key in self.file_matched_lines:
            self.file_matched_lines[file_key].clear()

        total_count = 0
        try:
            with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                line_num = 1
                for line in f:
                    match_count = self._count_matches(line)
                    if match_count > 0:
                        line_timestamp = parse_log_timestamp(line)
                        if self._is_in_datetime_range(line_timestamp):
                            total_count += match_count
                            self._add_matched_line(file_key, line_num, line, line_timestamp)
                            # Notify about each error found
                            if callback_error_found:
                                callback_error_found(filepath, line_num, line.strip())
                    line_num += 1
        except Exception:
            return

        self.file_error_counts[file_key] = total_count
        self.file_positions[file_key] = (current_size, current_mtime)

    def _should_watch_file(self, filepath):
        """Check if a file should be watched."""
        with self.lock:
            # Check if it's an indexed file
            if filepath in self.watch_files:
                return True
            # Check if it's in a watched directory
            for dir_path in self.watch_dirs:
                if filepath.startswith(dir_path) and filepath.endswith('.log'):
                    return True
        return False

    def _check_file_immediate(self, filepath):
        """Immediately check a file for new errors (called from FSEvents)."""
        try:
            self._check_file(filepath)
        except Exception:
            pass

    def start(self):
        """Start watching using FSEvents."""
        if self.running:
            return
        self.running = True

        # Create observer and event handler
        self.observer = Observer()
        self.event_handler = LogFileEventHandler(self)

        # Schedule watches for all directories and file parent directories
        self._update_watches()

        # Start the observer
        self.observer.start()

    def _update_watches(self):
        """Update FSEvents watches for current directories and files."""
        if not self.observer:
            return

        paths_to_watch = set()

        with self.lock:
            # Add watched directories
            for dir_path in self.watch_dirs:
                if Path(dir_path).exists():
                    paths_to_watch.add(dir_path)

            # Add parent directories of indexed files
            for filepath in self.watch_files:
                parent = str(Path(filepath).parent)
                if Path(parent).exists():
                    paths_to_watch.add(parent)

        # Add new watches
        for path in paths_to_watch:
            if path not in self.watched_paths:
                try:
                    self.observer.schedule(self.event_handler, path, recursive=False)
                    self.watched_paths.add(path)
                except Exception:
                    pass

    def stop(self):
        """Stop watching."""
        self.running = False
        if self.observer:
            self.observer.stop()
            self.observer.join(timeout=2)
            self.observer = None
        self.watched_paths.clear()

    def _check_all_files(self):
        """Check all watched files for new errors."""
        files_to_check = set()

        with self.lock:
            # Get files from directories
            for dir_path in self.watch_dirs:
                dir_obj = Path(dir_path)
                if dir_obj.exists():
                    for log_file in dir_obj.glob("*.log"):
                        files_to_check.add(str(log_file))

            # Add indexed files
            files_to_check.update(self.watch_files)

        # Check each file
        for filepath in files_to_check:
            try:
                self._check_file(filepath)
            except Exception:
                pass

    def _check_file(self, filepath):
        """Check a single file for new errors."""
        path = Path(filepath)
        if not path.exists():
            return

        file_key = str(filepath)
        try:
            current_size = path.stat().st_size
            current_mtime = path.stat().st_mtime
        except Exception:
            return

        if file_key not in self.file_positions:
            # First time seeing this file, start from end
            self.file_positions[file_key] = (current_size, current_mtime)
            if file_key not in self.file_error_counts:
                self.file_error_counts[file_key] = 0
            return

        last_position, last_mtime = self.file_positions[file_key]

        # Check if file was modified
        if current_mtime == last_mtime and current_size == last_position:
            return

        if current_size < last_position:
            # File was truncated/rotated
            last_position = 0
            if file_key in self.file_matched_lines:
                self.file_matched_lines[file_key].clear()

        if current_size == last_position:
            return

        # Count lines up to last_position to get starting line number
        start_line_num = 1
        try:
            with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                content_before = f.read(last_position)
                start_line_num = content_before.count('\n') + 1
        except Exception:
            pass

        # Read new content
        try:
            with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                f.seek(last_position)
                new_content = f.read()
        except Exception:
            return

        self.file_positions[file_key] = (current_size, current_mtime)

        # Check each new line for errors
        line_num = start_line_num
        for line in new_content.splitlines():
            match_count = self._count_matches(line)
            if match_count > 0:
                line_timestamp = parse_log_timestamp(line)
                if self._is_in_datetime_range(line_timestamp):
                    if file_key not in self.file_error_counts:
                        self.file_error_counts[file_key] = 0
                    self.file_error_counts[file_key] += match_count
                    self._add_matched_line(file_key, line_num, line, line_timestamp)
                    self.callback(path.name, filepath, line_num, line.strip())
            line_num += 1

    def _count_matches(self, line):
        """Count how many patterns match a line."""
        count = 0
        for pattern in self.error_patterns:
            if pattern.search(line):
                count += 1
        return count


class LogWatchMenuBar(rumps.App):
    """Menubar application for log watching."""

    def __init__(self):
        icon = str(ICON_PATH) if ICON_PATH.exists() else None
        super(LogWatchMenuBar, self).__init__("", icon=icon, quit_button=None)
        self.pid = os.getpid()
        self.title = "Logwatch"
        self.recent_errors = deque(maxlen=MAX_RECENT_ERRORS)
        self.config = self._load_config()
        self.index = self._load_index()
        self.sound_enabled = self.config.get("sound_enabled", True)
        self.start_datetime = self._parse_config_datetime("start_datetime")
        self.end_datetime = self._parse_config_datetime("end_datetime")
        self.watcher = None
        self.scanner = None
        self.scanning = False
        self.scan_progress = 0.0
        self.reindexing = False
        self.reindex_progress = 0.0
        self.sound_count = 0  # Track sounds played in current burst
        self.sound_reset_time = None  # Time to reset sound count
        self.max_sounds_per_burst = 5  # Maximum sounds to play in quick succession

        self._build_menu()
        self._start_watcher()

    def _parse_config_datetime(self, key):
        """Parse a datetime string from config."""
        dt_str = self.config.get(key)
        if dt_str:
            try:
                return datetime.strptime(dt_str, DATETIME_FORMAT)
            except ValueError:
                pass
        return None

    def _load_config(self):
        """Load configuration from file."""
        if CONFIG_PATH.exists():
            try:
                with open(CONFIG_PATH, "r") as f:
                    config = json.load(f)
                    # Migrate old single log_dir to directories list
                    if "log_dir" in config and "directories" not in config:
                        old_dir = config.pop("log_dir")
                        config["directories"] = [old_dir] if old_dir else []
                    return config
            except Exception:
                pass
        return {"directories": [], "sound_enabled": True}

    def _save_config(self):
        """Save configuration to file."""
        CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(CONFIG_PATH, "w") as f:
            json.dump(self.config, f, indent=2)

    def _load_index(self):
        """Load indexed log files with their metadata."""
        if INDEX_PATH.exists():
            try:
                with open(INDEX_PATH, "r") as f:
                    data = json.load(f)
                    # Migrate old format (list of files) to new format (dict with metadata)
                    if "files" in data and isinstance(data["files"], list):
                        if data["files"] and isinstance(data["files"][0], str):
                            # Old format: list of file paths
                            new_files = {}
                            for filepath in data["files"]:
                                new_files[filepath] = {
                                    "position": 0,
                                    "mtime": 0,
                                    "error_count": 0
                                }
                            data["files"] = new_files
                    return data
            except Exception:
                pass
        return {"files": {}}

    def _save_index(self):
        """Save indexed log files."""
        INDEX_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(INDEX_PATH, "w") as f:
            json.dump(self.index, f, indent=2)

    def _menu_item(self, title, callback=None, tooltip=None):
        """Create a menu item with optional tooltip."""
        item = rumps.MenuItem(title, callback=callback)
        if tooltip:
            item._menuitem.setToolTip_(tooltip)
        return item

    def _build_menu(self):
        """Build the dropdown menu."""
        self.menu.clear()

        # PID display for manual process management
        self.menu.add(self._menu_item(
            f"PID: {self.pid}",
            tooltip="Process ID - use 'kill {0}' in terminal to stop".format(self.pid)
        ))
        self.menu.add(rumps.separator)

        # Status section
        directories = self.config.get("directories", [])
        indexed_files = self.index.get("files", {})

        if directories or indexed_files:
            self.menu.add(self._menu_item(
                "Watching:",
                tooltip="Directories and files being monitored for matches"
            ))
            for d in directories:
                self.menu.add(self._menu_item(
                    f"  [DIR] {d}",
                    tooltip="All .log files in this directory are watched"
                ))
            if indexed_files:
                self.menu.add(self._menu_item(
                    f"  [IDX] {len(indexed_files)} indexed files",
                    tooltip="Individual log files added via scan"
                ))
        else:
            self.menu.add(self._menu_item(
                "No log sources configured",
                tooltip="Add directories or scan for log files to start monitoring"
            ))

        self.menu.add(rumps.separator)

        # Match count section
        total_matches = 0
        if self.watcher:
            total_matches = self.watcher.get_total_error_count()
        self.menu.add(self._menu_item(
            f"Total Matches: {total_matches}",
            tooltip="Total pattern matches found across all watched files"
        ))

        # Recent matches section with datetime range
        if self.recent_errors:
            # Get oldest and newest timestamps
            oldest_ts = self.recent_errors[-1][0]  # deque: newest first, oldest last
            newest_ts = self.recent_errors[0][0]
            if oldest_ts == newest_ts:
                time_range = oldest_ts
            else:
                time_range = f"{oldest_ts} - {newest_ts}"
            recent_label = f"Recent Matches ({time_range}):"
        else:
            recent_label = "Recent Matches:"
        self.menu.add(self._menu_item(
            recent_label,
            tooltip="Matches detected - select to choose editor"
        ))
        if self.recent_errors:
            for timestamp, filename, filepath, line_num, message in self.recent_errors:
                display_msg = message[:40] + "..." if len(message) > 40 else message
                item_text = f"  [{timestamp}] {filename}:{line_num}"
                # Create submenu with editor options for each recent match
                recent_item = self._menu_item(
                    item_text,
                    tooltip=display_msg
                )
                # Add enabled editors only
                editors = self._get_editors()
                for editor_id, config in editors.items():
                    if not config.get("enabled", True):
                        continue
                    line_info = f" - opens at line {line_num}" if config.get("supports_line", True) else ""
                    recent_item.add(self._menu_item(
                        config["name"],
                        callback=lambda _, fp=filepath, ln=line_num, eid=editor_id: self._open_in_editor(fp, ln, eid),
                        tooltip=f"{config['name']}{line_info}"
                    ))
                self.menu.add(recent_item)
        else:
            self.menu.add(self._menu_item("  (none)"))

        self.menu.add(rumps.separator)

        # Directory management
        dir_menu = self._menu_item(
            "Directories",
            tooltip="Manage watched directories"
        )
        dir_menu.add(self._menu_item(
            "Add Directory...",
            callback=self._add_directory,
            tooltip="Choose a directory to watch for .log files"
        ))
        if directories:
            dir_menu.add(rumps.separator)
            for d in directories:
                short_name = d if len(d) < 40 else "..." + d[-37:]
                dir_menu.add(self._menu_item(
                    f"Remove: {short_name}",
                    callback=lambda _, path=d: self._remove_directory(path),
                    tooltip=f"Stop watching {d}"
                ))
        self.menu.add(dir_menu)

        # Scan for log files
        scan_menu = self._menu_item(
            "Scan for Logs",
            tooltip="Find and index log files in a directory"
        )
        if self.scanning:
            progress_pct = self.scan_progress * 100
            scan_menu.add(self._menu_item(f"Scanning: {progress_pct:.1f}%"))
            scan_menu.add(self._menu_item(
                "Stop Scan",
                callback=self._stop_scan,
                tooltip="Cancel the current scan"
            ))
        else:
            scan_menu.add(self._menu_item(
                "Scan Directory...",
                callback=self._start_scan,
                tooltip="Recursively find log files and add them to index"
            ))
            if indexed_files:
                scan_menu.add(self._menu_item(
                    f"Clear Index ({len(indexed_files)} files)",
                    callback=self._clear_index,
                    tooltip="Remove all indexed files from monitoring"
                ))
        self.menu.add(scan_menu)

        # Indexed files submenu with match counts
        if indexed_files:
            idx_menu = self._menu_item(
                f"Indexed Files ({len(indexed_files)})",
                tooltip="Log files discovered by scanning"
            )
            # Add copy all paths option at the top
            idx_menu.add(self._menu_item(
                "Copy All Paths",
                callback=self._copy_all_paths,
                tooltip="Copy all monitored file paths to clipboard"
            ))
            idx_menu.add(rumps.separator)
            for filepath in sorted(indexed_files):
                match_count = 0
                matched_lines = []
                if self.watcher:
                    match_count = self.watcher.get_error_count(filepath)
                    matched_lines = self.watcher.get_matched_lines(filepath)
                filename = Path(filepath).name
                short_path = filepath if len(filepath) < 50 else "..." + filepath[-47:]
                # Create submenu for each file
                file_menu = self._menu_item(
                    f"{filename} [{match_count}]",
                    tooltip=filepath
                )
                file_menu.add(self._menu_item(
                    "View in Finder",
                    callback=lambda _, fp=filepath: self._reveal_in_finder(fp),
                    tooltip="Reveal file in Finder"
                ))
                # Open With submenu for editor choices (only enabled editors)
                open_menu = self._menu_item("Open With", tooltip="Choose application to open file")
                editors = self._get_editors()
                for editor_id, config in editors.items():
                    if not config.get("enabled", True):
                        continue
                    line_info = " (at line 1)" if config.get("supports_line", True) else ""
                    open_menu.add(self._menu_item(
                        config["name"],
                        callback=lambda _, fp=filepath, ln=1, eid=editor_id: self._open_in_editor(fp, ln, eid),
                        tooltip=f"{config.get('command', '')}{line_info}"
                    ))
                file_menu.add(open_menu)
                file_menu.add(rumps.separator)
                # View Matches submenu
                if matched_lines:
                    matches_menu = self._menu_item(
                        f"View Matches ({len(matched_lines)})",
                        tooltip="Lines matching patterns - opens editor submenu"
                    )
                    for match_tuple in matched_lines[-20:]:  # Show last 20
                        line_num, line_text = match_tuple[0], match_tuple[1]
                        display_text = line_text[:50] + "..." if len(line_text) > 50 else line_text
                        # Create submenu for each match with editor options
                        match_item = self._menu_item(
                            f"L{line_num}: {display_text}",
                            tooltip=f"Line {line_num} - choose editor to open"
                        )
                        # Add enabled editors only
                        for editor_id, config in editors.items():
                            if not config.get("enabled", True):
                                continue
                            line_info = f" - opens at line {line_num}" if config.get("supports_line", True) else ""
                            match_item.add(self._menu_item(
                                config["name"],
                                callback=lambda _, fp=filepath, ln=line_num, eid=editor_id: self._open_in_editor(fp, ln, eid),
                                tooltip=f"{config['name']}{line_info}"
                            ))
                        matches_menu.add(match_item)
                    file_menu.add(matches_menu)
                else:
                    file_menu.add(self._menu_item("View Matches (0)"))
                file_menu.add(rumps.separator)
                # Copy submenu
                copy_menu = self._menu_item("Copy", tooltip="Copy file path or file to clipboard")
                copy_menu.add(self._menu_item(
                    "Copy Path",
                    callback=lambda _, fp=filepath: self._copy_path(fp),
                    tooltip="Copy file path as text"
                ))
                copy_menu.add(self._menu_item(
                    "Copy File",
                    callback=lambda _, fp=filepath: self._copy_file(fp),
                    tooltip="Copy file to clipboard for pasting in Finder"
                ))
                file_menu.add(copy_menu)
                # Only show "Show Processes" if processes have the file open
                if self._has_file_processes(filepath):
                    file_menu.add(self._menu_item(
                        "Show Processes...",
                        callback=lambda _, fp=filepath: self._show_file_processes(fp),
                        tooltip="Show processes reading/writing this file"
                    ))
                file_menu.add(rumps.separator)
                file_menu.add(self._menu_item(f"Path: {short_path}"))
                file_menu.add(self._menu_item(
                    "Reset Count",
                    callback=lambda _, fp=filepath: self._reset_file_count(fp),
                    tooltip="Reset match count for this file to zero"
                ))
                file_menu.add(self._menu_item(
                    "Remove from Index",
                    callback=lambda _, fp=filepath: self._remove_indexed_file(fp),
                    tooltip="Stop watching this file"
                ))
                idx_menu.add(file_menu)
            self.menu.add(idx_menu)

        # Match patterns submenu
        patterns = self.config.get("error_patterns", DEFAULT_ERROR_PATTERNS)
        patterns_menu = self._menu_item(
            f"Match Patterns ({len(patterns)})",
            tooltip="Text patterns that trigger alerts when found in logs"
        )
        if self.reindexing:
            progress_pct = self.reindex_progress * 100
            patterns_menu.add(self._menu_item(f"Reindexing: {progress_pct:.1f}%"))
        else:
            patterns_menu.add(self._menu_item(
                "Add Pattern...",
                callback=self._add_pattern,
                tooltip="Add a new pattern to match"
            ))
        patterns_menu.add(rumps.separator)
        for pattern in patterns:
            # Create submenu for each pattern with Edit and Remove options
            pattern_submenu = self._menu_item(
                pattern[:25] + "..." if len(pattern) > 25 else pattern,
                tooltip=f"Options for pattern: {pattern}"
            )
            edit_item = self._menu_item(
                "Edit",
                tooltip=f"Modify this pattern"
            )
            remove_item = self._menu_item(
                "Remove",
                tooltip=f"Delete this pattern"
            )
            if not self.reindexing:
                edit_item.set_callback(lambda _, p=pattern: self._edit_pattern(p))
                remove_item.set_callback(lambda _, p=pattern: self._remove_pattern(p))
            pattern_submenu.add(edit_item)
            pattern_submenu.add(remove_item)
            patterns_menu.add(pattern_submenu)
        self.menu.add(patterns_menu)

        # Time filter submenu
        time_menu = self._menu_item(
            "Time Filter",
            tooltip="Only count matches within a specific time range"
        )
        start_str = self.start_datetime.strftime(DATETIME_FORMAT) if self.start_datetime else "Not set"
        end_str = self.end_datetime.strftime(DATETIME_FORMAT) if self.end_datetime else "Not set"
        time_menu.add(self._menu_item(
            f"Start: {start_str}",
            callback=self._edit_start_datetime,
            tooltip="Set start of time range filter"
        ))
        time_menu.add(self._menu_item(
            f"End: {end_str}",
            callback=self._edit_end_datetime,
            tooltip="Set end of time range filter"
        ))
        time_menu.add(rumps.separator)
        if self.start_datetime:
            time_menu.add(self._menu_item(
                "Clear Start",
                callback=self._clear_start_datetime,
                tooltip="Remove start time filter"
            ))
        if self.end_datetime:
            time_menu.add(self._menu_item(
                "Clear End",
                callback=self._clear_end_datetime,
                tooltip="Remove end time filter"
            ))
        if self.start_datetime or self.end_datetime:
            time_menu.add(self._menu_item(
                "Clear Both",
                callback=self._clear_datetime_filter,
                tooltip="Remove all time filters"
            ))
        self.menu.add(time_menu)

        self.menu.add(rumps.separator)

        # Actions
        if self.reindexing:
            progress_pct = self.reindex_progress * 100
            self.menu.add(self._menu_item(f"Re-scanning: {progress_pct:.0f}%"))
        else:
            self.menu.add(self._menu_item(
                "Re-scan Files (with sound)",
                callback=self._rescan_with_sound,
                tooltip="Re-read all files and play sound for each match found"
            ))
        self.menu.add(self._menu_item(
            "Reset Counter",
            callback=self._reset_counter,
            tooltip="Reset all match counts to zero"
        ))
        self.menu.add(self._menu_item(
            "Clear Recent Matches",
            callback=self._clear_errors,
            tooltip="Clear the recent matches list"
        ))

        # Sound submenu
        sound_menu = self._menu_item(
            "Sound",
            tooltip="Configure alert sound settings"
        )
        sound_status = "ON" if self.sound_enabled else "OFF"
        sound_menu.add(self._menu_item(
            f"Enabled: {sound_status}",
            callback=self._toggle_sound,
            tooltip="Toggle sound alerts on/off"
        ))
        sound_menu.add(rumps.separator)

        # Current sound display and system sounds list
        current_sound = self.config.get("sound_path", DEFAULT_SOUND)

        # System sounds selection - click selects, plays once, and closes menu
        system_sounds = self._get_system_sounds()
        for sound_name, sound_path in system_sounds:
            is_current = sound_path == current_sound
            prefix = "*" if is_current else "  "
            title = f"{prefix} {sound_name}"
            sound_menu.add(self._menu_item(
                title,
                callback=lambda _, sp=sound_path: self._select_sound(sp),
                tooltip="Click to select this sound"
            ))

        sound_menu.add(rumps.separator)
        sound_menu.add(self._menu_item(
            "Choose Custom File...",
            callback=self._choose_custom_sound,
            tooltip="Select a custom sound file"
        ))

        self.menu.add(sound_menu)

        # Editors settings submenu
        editors_menu = self._menu_item(
            "Editors",
            tooltip="Configure external editors for opening log files"
        )
        editors = self._get_editors()
        for editor_id, config in editors.items():
            enabled = config.get("enabled", True)
            status = "ON" if enabled else "OFF"
            editor_item = self._menu_item(
                f"{config['name']} [{status}]",
                tooltip=f"Command: {config.get('command', 'not set')}"
            )
            editor_item.add(self._menu_item(
                "Toggle Enable/Disable",
                callback=lambda _, eid=editor_id: self._toggle_editor(eid),
                tooltip="Enable or disable this editor in menus"
            ))
            editor_item.add(self._menu_item(
                "Locate...",
                callback=lambda _, eid=editor_id: self._locate_editor(eid),
                tooltip="Find where this editor is installed"
            ))
            editor_item.add(self._menu_item(
                "Edit Command...",
                callback=lambda _, eid=editor_id: self._edit_editor_command(eid),
                tooltip="Modify the command used to open files"
            ))
            editor_item.add(self._menu_item(
                "Reset to Default",
                callback=lambda _, eid=editor_id: self._reset_editor(eid),
                tooltip="Restore default command for this editor"
            ))
            editors_menu.add(editor_item)
        self.menu.add(editors_menu)

        self.menu.add(rumps.separator)
        self.menu.add(self._menu_item(
            "Restart",
            callback=self._restart,
            tooltip="Restart the application"
        ))
        self.menu.add(self._menu_item(
            "Quit",
            callback=self._quit,
            tooltip="Stop monitoring and exit"
        ))

    def _start_watcher(self, reindex=True):
        """Start or restart the log watcher."""
        if self.watcher:
            self.watcher.stop()

        error_patterns = self.config.get("error_patterns", DEFAULT_ERROR_PATTERNS)
        self.watcher = MultiLogWatcher(self._on_error_detected, error_patterns)
        self.watcher.set_directories(self.config.get("directories", []))
        self.watcher.set_datetime_filter(self.start_datetime, self.end_datetime)

        # Get file paths from index (now a dict)
        indexed_files = self.index.get("files", {})
        self.watcher.set_indexed_files(list(indexed_files.keys()))

        # Restore saved state and reindex from saved positions
        if indexed_files:
            self.watcher.restore_file_state(indexed_files)
            if reindex:
                self.reindexing = True
                self.reindex_progress = 0.0
                self._build_menu()

                def do_reindex():
                    self.watcher.reindex_from_positions(self._on_reindex_progress)
                    self._update_index_from_watcher()
                    self.reindexing = False
                    self._build_menu()

                thread = threading.Thread(target=do_reindex, daemon=True)
                thread.start()

        self.watcher.start()

        directories = self.config.get("directories", [])
        if directories or indexed_files:
            self.title = "Logwatch"
        else:
            self.title = "Logwatch?"

    def _on_error_detected(self, filename, filepath, line_num, message):
        """Called when an error is detected (from background thread)."""
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.recent_errors.appendleft((timestamp, filename, filepath, line_num, message))

        # Play sound with burst limiting (max 5 sounds in 2 seconds)
        if self.sound_enabled:
            now = datetime.now()
            # Reset counter if enough time has passed since last burst
            if self.sound_reset_time is None or now > self.sound_reset_time:
                self.sound_count = 0

            if self.sound_count < self.max_sounds_per_burst:
                self._play_sound()
                self.sound_count += 1
                # Reset counter 2 seconds after first sound in burst
                if self.sound_count == 1:
                    self.sound_reset_time = now + timedelta(seconds=2)

        # Schedule UI updates on main thread
        def update_ui():
            self.title = "Logwatch!"
            self._build_menu()

        AppHelper.callAfter(update_ui)

    def _play_sound(self):
        """Play alert sound."""
        sound_path = self.config.get("sound_path", DEFAULT_SOUND)
        try:
            subprocess.Popen(
                ["afplay", sound_path],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except Exception:
            pass

    def _play_sound_file(self, sound_path):
        """Play a specific sound file."""
        try:
            subprocess.Popen(
                ["afplay", sound_path],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except Exception:
            pass

    def _select_folder(self, prompt="Select a folder"):
        """Show native macOS folder picker dialog."""
        script = f'''
        set folderPath to POSIX path of (choose folder with prompt "{prompt}")
        return folderPath
        '''
        try:
            result = subprocess.run(
                ["osascript", "-e", script],
                capture_output=True,
                text=True,
                timeout=120
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except subprocess.TimeoutExpired:
            pass
        except Exception:
            pass
        return None

    def _add_directory(self, _):
        """Add a directory to watch."""
        dir_path = self._select_folder("Select a log directory to watch")
        if dir_path:
            # Remove trailing slash if present
            dir_path = dir_path.rstrip("/")
            if Path(dir_path).is_dir():
                directories = self.config.get("directories", [])
                if dir_path not in directories:
                    directories.append(dir_path)
                    self.config["directories"] = directories
                    self._save_config()
                    # Restart watcher in background to avoid blocking UI
                    def restart():
                        self._start_watcher()
                        AppHelper.callAfter(self._build_menu)
                    threading.Thread(target=restart, daemon=True).start()

    def _remove_directory(self, dir_path):
        """Remove a directory from watch list."""
        directories = self.config.get("directories", [])
        if dir_path in directories:
            directories.remove(dir_path)
            self.config["directories"] = directories
            self._save_config()
            # Restart watcher in background to avoid blocking UI
            def restart():
                self._start_watcher()
                AppHelper.callAfter(self._build_menu)
            threading.Thread(target=restart, daemon=True).start()

    def _start_scan(self, _):
        """Start scanning for log files."""
        scan_path = self._select_folder("Select a directory to scan for log files")
        if scan_path:
            # Remove trailing slash if present
            scan_path = scan_path.rstrip("/")
            if Path(scan_path).is_dir():
                self.scanning = True
                self.scan_progress = 0.0
                self._build_menu()
                self.scanner = LogScanner(
                    self._on_log_found,
                    self._on_scan_complete,
                    self._on_scan_progress
                )
                self.scanner.start_scan(scan_path)

    def _on_log_found(self, filepath):
        """Called when scanner finds a log file."""
        files = self.index.get("files", {})
        if filepath not in files:
            files[filepath] = {"position": 0, "mtime": 0, "error_count": 0}
            self.index["files"] = files
            if self.watcher:
                self.watcher.add_indexed_file(filepath)

    def _on_scan_progress(self, progress):
        """Called with scan progress updates (from background thread)."""
        self.scan_progress = progress
        # Schedule UI update on main thread
        AppHelper.callAfter(self._build_menu)

    def _on_scan_complete(self, count):
        """Called when scan completes (from background thread)."""
        self.scanning = False
        self.scan_progress = 1.0
        self._save_index()
        # Schedule UI update on main thread
        AppHelper.callAfter(self._build_menu)

    def _stop_scan(self, _):
        """Stop the current scan."""
        if self.scanner:
            self.scanner.stop()
        self.scanning = False
        self._save_index()
        self._build_menu()

    def _clear_index(self, _):
        """Clear the indexed files."""
        self.index["files"] = {}
        self._save_index()
        # Restart watcher in background to avoid blocking UI
        def restart():
            self._start_watcher()
            AppHelper.callAfter(self._build_menu)
        threading.Thread(target=restart, daemon=True).start()

    def _reset_counter(self, _):
        """Reset match counter."""
        if self.watcher:
            self.watcher.reset_counts()
        self.title = "Logwatch"
        self._build_menu()

    def _clear_errors(self, _):
        """Clear recent matches."""
        self.recent_errors.clear()
        self.title = "Logwatch"
        self._build_menu()

    def _rescan_with_sound(self, _):
        """Re-scan all indexed files and play sound sequence for matches found."""
        if not self.watcher or self.reindexing:
            return

        self.reindexing = True
        self.reindex_progress = 0.0
        self._build_menu()

        error_count = [0]  # Use list to allow modification in nested function

        def on_error_found(filepath, line_num, message):
            """Called for each error found during rescan."""
            error_count[0] += 1

        def do_rescan():
            self.watcher.reindex_all_files(
                callback_progress=self._on_reindex_progress,
                callback_error_found=on_error_found
            )
            self.reindexing = False

            # Play up to 5 distinct sounds after scan completes
            if self.sound_enabled and error_count[0] > 0:
                sounds_to_play = min(error_count[0], 5)
                for i in range(sounds_to_play):
                    self._play_sound()
                    if i < sounds_to_play - 1:
                        import time
                        time.sleep(0.7)  # Pause between sounds for distinct repetition

            AppHelper.callAfter(self._build_menu)

        thread = threading.Thread(target=do_rescan, daemon=True)
        thread.start()

    def _toggle_sound(self, _):
        """Toggle sound alerts."""
        self.sound_enabled = not self.sound_enabled
        self.config["sound_enabled"] = self.sound_enabled
        self._save_config()
        self._build_menu()

    def _get_system_sounds(self):
        """Get list of available macOS system sounds."""
        sounds = []
        system_sounds_dir = Path("/System/Library/Sounds")
        if system_sounds_dir.exists():
            for sound_file in sorted(system_sounds_dir.glob("*.aiff")):
                sounds.append((sound_file.stem, str(sound_file)))
        return sounds

    def _show_sound_picker(self, _):
        """Show a dialog to pick and preview sounds."""
        from AppKit import NSPopUpButton, NSButton, NSOnState, NSOffState

        alert = NSAlert.alloc().init()
        alert.setMessageText_("Choose Alert Sound")
        alert.setInformativeText_("Select a sound and click Preview to hear it.")
        alert.addButtonWithTitle_("OK")
        alert.addButtonWithTitle_("Cancel")

        # Create container view
        container = NSView.alloc().initWithFrame_(NSMakeRect(0, 0, 300, 70))

        # Create popup button for sound selection
        popup = NSPopUpButton.alloc().initWithFrame_pullsDown_(NSMakeRect(0, 35, 220, 25), False)

        # Add sounds to popup
        system_sounds = self._get_system_sounds()
        current_sound = self.config.get("sound_path", DEFAULT_SOUND)
        selected_index = 0

        for i, (sound_name, sound_path) in enumerate(system_sounds):
            popup.addItemWithTitle_(sound_name)
            popup.lastItem().setRepresentedObject_(sound_path)
            if sound_path == current_sound:
                selected_index = i

        popup.selectItemAtIndex_(selected_index)

        # Store popup reference for preview button
        self._sound_picker_popup = popup
        self._sound_picker_sounds = system_sounds

        # Create preview button
        preview_btn = NSButton.alloc().initWithFrame_(NSMakeRect(230, 35, 70, 25))
        preview_btn.setTitle_("Preview")
        preview_btn.setBezelStyle_(1)  # NSBezelStyleRounded
        preview_btn.setTarget_(self)
        preview_btn.setAction_(self._preview_selected_sound)

        container.addSubview_(popup)
        container.addSubview_(preview_btn)

        alert.setAccessoryView_(container)

        # Run the dialog
        response = alert.runModal()

        if response == 1000:  # OK
            selected_idx = popup.indexOfSelectedItem()
            if 0 <= selected_idx < len(system_sounds):
                sound_path = system_sounds[selected_idx][1]
                self.config["sound_path"] = sound_path
                self._save_config()
                self._build_menu()

        # Cleanup
        self._sound_picker_popup = None
        self._sound_picker_sounds = None

    def _preview_selected_sound(self):
        """Preview the currently selected sound in the picker."""
        if hasattr(self, '_sound_picker_popup') and self._sound_picker_popup:
            selected_idx = self._sound_picker_popup.indexOfSelectedItem()
            if hasattr(self, '_sound_picker_sounds') and self._sound_picker_sounds:
                if 0 <= selected_idx < len(self._sound_picker_sounds):
                    sound_path = self._sound_picker_sounds[selected_idx][1]
                    try:
                        subprocess.Popen(
                            ["afplay", sound_path],
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL,
                        )
                    except Exception:
                        pass

    def _select_sound(self, sound_path):
        """Select a sound for alerts."""
        self.config["sound_path"] = sound_path
        self._save_config()
        self._build_menu()
        # Play the selected sound as preview
        self._play_sound()

    def _choose_custom_sound(self, _):
        """Choose a custom sound file."""
        script = '''
        set soundFile to POSIX path of (choose file with prompt "Select a sound file" of type {"public.audio"})
        return soundFile
        '''
        try:
            result = subprocess.run(
                ["osascript", "-e", script],
                capture_output=True,
                text=True,
                timeout=120
            )
            if result.returncode == 0:
                sound_path = result.stdout.strip()
                if sound_path:
                    self.config["sound_path"] = sound_path
                    self._save_config()
                    self._build_menu()
                    self._play_sound()
        except subprocess.TimeoutExpired:
            pass
        except Exception:
            pass

    def _test_sound(self, _):
        """Play the current alert sound."""
        self._play_sound()

    def _edit_start_datetime(self, _):
        """Edit the start datetime filter."""
        result = show_datetime_picker(
            "Set Start Time",
            "Only matches after this time will be counted:",
            self.start_datetime
        )
        if result == 'clear':
            self._clear_start_datetime(None)
        elif result:
            self.start_datetime = result
            self.config["start_datetime"] = result.strftime(DATETIME_FORMAT)
            self._save_config()
            self._reindex_with_new_filter()

    def _edit_end_datetime(self, _):
        """Edit the end datetime filter."""
        result = show_datetime_picker(
            "Set End Time",
            "Only matches before this time will be counted:",
            self.end_datetime
        )
        if result == 'clear':
            self._clear_end_datetime(None)
        elif result:
            self.end_datetime = result
            self.config["end_datetime"] = result.strftime(DATETIME_FORMAT)
            self._save_config()
            self._reindex_with_new_filter()

    def _clear_start_datetime(self, _):
        """Clear the start datetime filter."""
        self.start_datetime = None
        if "start_datetime" in self.config:
            del self.config["start_datetime"]
        self._save_config()
        self._reindex_with_new_filter()

    def _clear_end_datetime(self, _):
        """Clear the end datetime filter."""
        self.end_datetime = None
        if "end_datetime" in self.config:
            del self.config["end_datetime"]
        self._save_config()
        self._reindex_with_new_filter()

    def _clear_datetime_filter(self, _):
        """Clear both start and end datetime filters."""
        self.start_datetime = None
        self.end_datetime = None
        if "start_datetime" in self.config:
            del self.config["start_datetime"]
        if "end_datetime" in self.config:
            del self.config["end_datetime"]
        self._save_config()
        self._reindex_with_new_filter()

    def _reindex_with_new_filter(self):
        """Reindex all files with updated datetime filter."""
        self.reindexing = True
        self.reindex_progress = 0.0
        self._build_menu()

        def do_reindex():
            if self.watcher:
                self.watcher.set_datetime_filter(self.start_datetime, self.end_datetime)
                self.watcher.reindex_all_files(self._on_reindex_progress)
            self.reindexing = False
            self._build_menu()

        thread = threading.Thread(target=do_reindex, daemon=True)
        thread.start()

    def _reset_file_count(self, filepath):
        """Reset match count for a specific file."""
        if self.watcher:
            self.watcher.reset_file_count(filepath)
        self._build_menu()

    def _reveal_in_finder(self, filepath):
        """Reveal a file in Finder."""
        try:
            subprocess.run(["open", "-R", filepath], check=False)
        except Exception:
            pass

    def _open_file(self, filepath):
        """Open a file in the default application."""
        try:
            subprocess.run(["open", filepath], check=False)
        except Exception:
            pass

    def _get_editors(self):
        """Get editor configurations from config, merging with defaults."""
        saved_editors = self.config.get("editors", {})
        editors = {}
        for editor_id, default_config in DEFAULT_EDITORS.items():
            if editor_id in saved_editors:
                # Merge saved config with defaults
                editors[editor_id] = {**default_config, **saved_editors[editor_id]}
            else:
                editors[editor_id] = default_config.copy()
        return editors

    def _open_in_editor(self, filepath, line_num, editor_id):
        """Open a file at a specific line in the chosen editor."""
        editors = self._get_editors()
        editor_config = editors.get(editor_id)

        if not editor_config:
            self._show_alert("Error", f"Unknown editor: {editor_id}")
            return

        if not editor_config.get("enabled", True):
            self._show_alert("Editor Disabled", f"{editor_config['name']} is disabled in settings.")
            return

        # Build command from template
        command_template = editor_config.get("command", "")
        command_str = command_template.replace("{file}", f'"{filepath}"').replace("{line}", str(line_num))

        try:
            if editor_config.get("use_terminal"):
                # Run in Terminal using AppleScript
                script = f'tell application "Terminal" to do script "{command_str}"'
                subprocess.run(["osascript", "-e", script], check=False)
            else:
                # Run command directly via shell
                result = subprocess.run(command_str, shell=True, capture_output=True, timeout=5)
                if result.returncode != 0:
                    self._show_alert(
                        "Editor Not Found",
                        f"Could not open {editor_config['name']}.\nCommand: {command_str}\nMake sure it's installed and in your PATH."
                    )
        except FileNotFoundError:
            self._show_alert(
                "Editor Not Found",
                f"Could not find {editor_config['name']}. Make sure it's installed."
            )
        except subprocess.TimeoutExpired:
            pass  # Editor probably opened fine, just didn't exit
        except Exception as e:
            self._show_alert("Error", f"Failed to open editor: {e}")

    def _open_in_console(self, filepath):
        """Open a log file in Console.app."""
        try:
            subprocess.run(["open", "-a", "Console", filepath], check=False)
        except Exception:
            pass

    def _toggle_editor(self, editor_id):
        """Toggle an editor's enabled state."""
        editors = self.config.get("editors", {})
        if editor_id not in editors:
            editors[editor_id] = {}
        current = editors[editor_id].get("enabled", DEFAULT_EDITORS.get(editor_id, {}).get("enabled", True))
        editors[editor_id]["enabled"] = not current
        self.config["editors"] = editors
        self._save_config()
        self._build_menu()

    def _edit_editor_command(self, editor_id):
        """Edit the command for an editor."""
        editors = self._get_editors()
        editor_config = editors.get(editor_id, {})
        current_command = editor_config.get("command", "")

        NSApp.activateIgnoringOtherApps_(True)
        alert = NSAlert.alloc().init()
        alert.setMessageText_(f"Edit {editor_config.get('name', editor_id)} Command")
        alert.setInformativeText_(
            "Use {file} for the file path and {line} for the line number.\n"
            "Example: code --goto {file}:{line}"
        )
        alert.addButtonWithTitle_("Save")
        alert.addButtonWithTitle_("Cancel")

        # Create text field for command
        text_field = NSTextField.alloc().initWithFrame_(NSMakeRect(0, 0, 400, 24))
        text_field.setStringValue_(current_command)
        text_field.setFont_(NSFont.userFixedPitchFontOfSize_(12))
        alert.setAccessoryView_(text_field)
        alert.window().setLevel_(3)

        response = alert.runModal()
        if response == 1000:  # Save
            new_command = text_field.stringValue().strip()
            if new_command:
                saved_editors = self.config.get("editors", {})
                if editor_id not in saved_editors:
                    saved_editors[editor_id] = {}
                saved_editors[editor_id]["command"] = new_command
                self.config["editors"] = saved_editors
                self._save_config()
                self._build_menu()

    def _reset_editor(self, editor_id):
        """Reset an editor to its default configuration."""
        saved_editors = self.config.get("editors", {})
        if editor_id in saved_editors:
            del saved_editors[editor_id]
            self.config["editors"] = saved_editors
            self._save_config()
            self._build_menu()

    def _locate_editor(self, editor_id):
        """Find where an editor is installed and display the results."""
        editors = self._get_editors()
        editor = editors.get(editor_id)
        if not editor:
            return

        editor_name = editor.get("name", editor_id)
        command = editor.get("command", "")

        # Extract the command name (first word before any arguments)
        cmd_name = command.split()[0] if command else ""

        locations = []

        # Try 'which' to find command in PATH
        if cmd_name:
            try:
                result = subprocess.run(
                    ["which", cmd_name],
                    capture_output=True,
                    text=True,
                    timeout=2
                )
                if result.returncode == 0 and result.stdout.strip():
                    locations.append(("PATH", result.stdout.strip()))
            except (subprocess.TimeoutExpired, Exception):
                pass

        # Check common macOS application paths
        app_paths = {
            "console": ["/System/Applications/Utilities/Console.app"],
            "vscode": [
                "/Applications/Visual Studio Code.app",
                "~/Applications/Visual Studio Code.app",
            ],
            "sublime": [
                "/Applications/Sublime Text.app",
                "~/Applications/Sublime Text.app",
            ],
            "bbedit": [
                "/Applications/BBEdit.app",
                "~/Applications/BBEdit.app",
            ],
            "emacs": [
                "/Applications/Emacs.app",
                "~/Applications/Emacs.app",
                "/opt/homebrew/bin/emacs",
                "/usr/local/bin/emacs",
            ],
            "textmate": [
                "/Applications/TextMate.app",
                "~/Applications/TextMate.app",
            ],
            "vim": [
                "/opt/homebrew/bin/vim",
                "/usr/local/bin/vim",
                "/usr/bin/vim",
            ],
        }

        if editor_id in app_paths:
            for app_path in app_paths[editor_id]:
                expanded = os.path.expanduser(app_path)
                if os.path.exists(expanded):
                    locations.append(("App", expanded))

        # Display results
        NSApp.activateIgnoringOtherApps_(True)
        alert = NSAlert.alloc().init()
        alert.setMessageText_(f"Locate: {editor_name}")

        if locations:
            info_lines = []
            for loc_type, loc_path in locations:
                info_lines.append(f"{loc_type}: {loc_path}")
            alert.setInformativeText_("\n".join(info_lines))
        else:
            alert.setInformativeText_(
                f"'{cmd_name}' was not found.\n\n"
                "Check that the editor is installed and the command is correct."
            )

        alert.addButtonWithTitle_("OK")
        if locations:
            alert.addButtonWithTitle_("Copy Path")
        alert.window().setLevel_(3)

        response = alert.runModal()
        if response == 1001 and locations:  # Copy Path
            # Copy the first location path
            path_to_copy = locations[0][1]
            subprocess.run(["pbcopy"], input=path_to_copy.encode("utf-8"), check=False)

    def _get_process_details(self, pid):
        """Get detailed information about a process by PID."""
        details = {}
        try:
            # Get process path using ps
            result = subprocess.run(
                ["ps", "-p", pid, "-o", "command="],
                capture_output=True,
                text=True,
                timeout=2
            )
            if result.returncode == 0:
                details["path"] = result.stdout.strip()

            # Get more info using ps
            result = subprocess.run(
                ["ps", "-p", pid, "-o", "pid=,ppid=,%cpu=,%mem=,etime=,state="],
                capture_output=True,
                text=True,
                timeout=2
            )
            if result.returncode == 0:
                parts = result.stdout.strip().split()
                if len(parts) >= 5:
                    details["ppid"] = parts[1]
                    details["cpu"] = parts[2] + "%"
                    details["mem"] = parts[3] + "%"
                    details["elapsed"] = parts[4]
                    if len(parts) >= 6:
                        details["state"] = parts[5]
        except Exception:
            pass
        return details

    def _has_file_processes(self, filepath):
        """Check if any processes have this file open."""
        try:
            result = subprocess.run(
                ["lsof", filepath],
                capture_output=True,
                text=True,
                timeout=2
            )
            output = result.stdout.strip()
            if output:
                lines = output.split("\n")
                # More than just header line means processes found
                return len(lines) > 1
            return False
        except (subprocess.TimeoutExpired, Exception):
            return False

    def _show_file_processes(self, filepath):
        """Show processes that have this file open using lsof."""
        try:
            result = subprocess.run(
                ["lsof", filepath],
                capture_output=True,
                text=True,
                timeout=5
            )
            output = result.stdout.strip()

            NSApp.activateIgnoringOtherApps_(True)
            alert = NSAlert.alloc().init()
            alert.setMessageText_(f"Processes: {Path(filepath).name}")

            if output:
                # Parse lsof output
                lines = output.split("\n")
                process_info = []
                seen_pids = set()
                if len(lines) > 1:  # Skip header
                    for line in lines[1:]:
                        parts = line.split()
                        if len(parts) >= 9:
                            cmd = parts[0]
                            pid = parts[1]
                            user = parts[2]
                            fd = parts[3]

                            # Skip duplicate PIDs
                            if pid in seen_pids:
                                continue
                            seen_pids.add(pid)

                            # Determine read/write mode from FD column
                            mode = "unknown"
                            if "r" in fd.lower() and "w" in fd.lower():
                                mode = "read/write"
                            elif "r" in fd.lower():
                                mode = "read"
                            elif "w" in fd.lower():
                                mode = "write"

                            # Get additional process details
                            details = self._get_process_details(pid)

                            info_lines = [f"{cmd} (PID {pid}) - {mode}"]
                            if details.get("path"):
                                path = details["path"]
                                if len(path) > 60:
                                    path = "..." + path[-57:]
                                info_lines.append(f"  Path: {path}")
                            if details.get("cpu") and details.get("mem"):
                                info_lines.append(f"  CPU: {details['cpu']}, Mem: {details['mem']}")
                            if details.get("elapsed"):
                                info_lines.append(f"  Running: {details['elapsed']}")
                            if details.get("ppid"):
                                info_lines.append(f"  Parent PID: {details['ppid']}")

                            process_info.append("\n".join(info_lines))

                if process_info:
                    info_text = "\n\n".join(process_info)
                else:
                    info_text = "Could not parse process information"
            else:
                info_text = "No processes have this file open"

            alert.setInformativeText_(info_text)
            alert.addButtonWithTitle_("OK")
            alert.addButtonWithTitle_("Open Activity Monitor")
            alert.window().setLevel_(3)

            response = alert.runModal()
            if response == 1001:  # Open Activity Monitor
                subprocess.run(["open", "-a", "Activity Monitor"], check=False)

        except subprocess.TimeoutExpired:
            self._show_alert("Timeout", "lsof command timed out")
        except Exception as e:
            self._show_alert("Error", f"Could not get process info: {e}")

    def _show_alert(self, title, message):
        """Show a simple alert dialog."""
        NSApp.activateIgnoringOtherApps_(True)
        alert = NSAlert.alloc().init()
        alert.setMessageText_(title)
        alert.setInformativeText_(message)
        alert.addButtonWithTitle_("OK")
        alert.window().setLevel_(3)
        alert.runModal()

    def _copy_path(self, filepath):
        """Copy file path to clipboard."""
        try:
            subprocess.run(
                ["pbcopy"],
                input=filepath.encode("utf-8"),
                check=False
            )
        except Exception:
            pass

    def _copy_all_paths(self, _):
        """Copy all monitored file paths to clipboard."""
        indexed_files = self.index.get("files", {})
        directories = self.config.get("directories", [])

        paths = []
        # Add directories
        for d in directories:
            paths.append(f"[DIR] {d}")
        # Add indexed files
        for filepath in sorted(indexed_files.keys()):
            paths.append(filepath)

        if paths:
            text = "\n".join(paths)
            try:
                subprocess.run(
                    ["pbcopy"],
                    input=text.encode("utf-8"),
                    check=False
                )
            except Exception:
                pass

    def _copy_file(self, filepath):
        """Copy file to clipboard using AppleScript."""
        script = f'''
        set theFile to POSIX file "{filepath}"
        tell application "Finder"
            set the clipboard to (theFile as alias)
        end tell
        '''
        try:
            subprocess.run(
                ["osascript", "-e", script],
                capture_output=True,
                timeout=5
            )
        except Exception:
            pass

    def _remove_indexed_file(self, filepath):
        """Remove a file from the index."""
        files = self.index.get("files", {})
        if filepath in files:
            del files[filepath]
            self.index["files"] = files
            self._save_index()
            # Restart watcher in background to avoid blocking UI
            def restart():
                self._start_watcher()
                AppHelper.callAfter(self._build_menu)
            threading.Thread(target=restart, daemon=True).start()

    def _add_pattern(self, _):
        """Add a new match pattern."""
        indexed_files = self.index.get("files", {})
        pattern = show_pattern_editor("Add Match Pattern", indexed_files=indexed_files)

        if pattern:
            patterns = self.config.get("error_patterns", DEFAULT_ERROR_PATTERNS.copy())
            if pattern not in patterns:
                patterns.append(pattern)
                self.config["error_patterns"] = patterns
                self._save_config()
                self._reindex_with_new_patterns()

    def _edit_pattern(self, old_pattern):
        """Edit an existing match pattern."""
        indexed_files = self.index.get("files", {})
        new_pattern = show_pattern_editor("Edit Match Pattern", old_pattern, indexed_files=indexed_files)

        if new_pattern and new_pattern != old_pattern:
            patterns = self.config.get("error_patterns", DEFAULT_ERROR_PATTERNS.copy())
            if old_pattern in patterns:
                idx = patterns.index(old_pattern)
                patterns[idx] = new_pattern
                self.config["error_patterns"] = patterns
                self._save_config()
                self._reindex_with_new_patterns()

    def _remove_pattern(self, pattern):
        """Remove a match pattern."""
        patterns = self.config.get("error_patterns", DEFAULT_ERROR_PATTERNS.copy())
        if pattern in patterns:
            patterns.remove(pattern)
            self.config["error_patterns"] = patterns
            self._save_config()
            self._reindex_with_new_patterns()

    def _reindex_with_new_patterns(self):
        """Reindex all files with updated patterns."""
        self.reindexing = True
        self.reindex_progress = 0.0
        self._build_menu()

        def do_reindex():
            error_patterns = self.config.get("error_patterns", DEFAULT_ERROR_PATTERNS)
            if self.watcher:
                self.watcher.set_error_patterns(error_patterns)
                self.watcher.reindex_all_files(self._on_reindex_progress)
            self.reindexing = False
            self._build_menu()

        thread = threading.Thread(target=do_reindex, daemon=True)
        thread.start()

    def _on_reindex_progress(self, progress):
        """Called with reindex progress updates."""
        self.reindex_progress = progress

    def _update_index_from_watcher(self):
        """Update index with current watcher state."""
        if self.watcher:
            self.index["files"] = self.watcher.get_file_state()
            self._save_index()

    def _restart(self, _):
        """Restart the application."""
        self._update_index_from_watcher()
        if self.watcher:
            self.watcher.stop()
        if self.scanner:
            self.scanner.stop()

        # Launch new instance before quitting
        script_path = Path(__file__).resolve()
        subprocess.Popen(
            ["python3", str(script_path)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True
        )
        rumps.quit_application()

    def _quit(self, _):
        """Quit the application."""
        self._update_index_from_watcher()
        if self.watcher:
            self.watcher.stop()
        if self.scanner:
            self.scanner.stop()
        rumps.quit_application()


def set_high_priority():
    """Set the process to high priority for responsive sound alerts."""
    try:
        # On macOS, try to set nice value lower (higher priority)
        # Nice values: -20 (highest) to 19 (lowest), 0 is default
        # Without root we can only increase nice (lower priority),
        # but we can try -5 and it may work depending on permissions
        current_nice = os.nice(0)  # Get current nice value
        if current_nice >= 0:
            try:
                # Try to decrease nice value (increase priority)
                os.nice(-5)
            except PermissionError:
                # Without elevated permissions, this is expected
                pass
    except Exception:
        pass


if __name__ == "__main__":
    set_high_priority()
    app = LogWatchMenuBar()
    app.run()
