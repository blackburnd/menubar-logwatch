"""
Core functionality for logwatch-menubar - no macOS GUI dependencies.

This module contains the log watching, scanning, and parsing logic that can be
tested independently of the macOS menubar UI.
"""

import os
import re
import json
import threading
from pathlib import Path
from datetime import datetime
from collections import deque

# Default patterns that indicate an error or exception
# Each pattern is a dict with 'title' (display name) and 'pattern' (match string)
DEFAULT_ERROR_PATTERNS = [
    {"title": "Exceptions", "pattern": "exception"},
    {"title": "Errors", "pattern": "error"},
    {"title": "Tracebacks", "pattern": "traceback"},
    {"title": "Failures", "pattern": "failed"},
    {"title": "Critical", "pattern": "critical"},
]


def normalize_pattern(p):
    """Convert pattern to normalized dict format.

    Handles migration from old string format to new dict format.
    """
    if isinstance(p, str):
        return {"title": p.capitalize(), "pattern": p}
    if isinstance(p, dict) and "pattern" in p:
        if "title" not in p:
            p["title"] = p["pattern"].capitalize()
        return p
    return {"title": str(p), "pattern": str(p)}


def normalize_patterns(patterns):
    """Normalize a list of patterns to dict format."""
    return [normalize_pattern(p) for p in patterns]

# Default pattern to detect log file format (timestamp at start of line)
DEFAULT_LOG_LINE_PATTERN = (
    r"^\d{4}[-/]\d{2}[-/]\d{2}|"  # 2024-01-01 or 2024/01/01
    r"^\d{2}[-/]\d{2}[-/]\d{4}|"  # 01-01-2024 or 01/01/2024
    r"^\[\d{4}[-/]\d{2}[-/]\d{2}|"  # [2024-01-01
    r"^\d{2}:\d{2}:\d{2}|"  # 12:30:45
    r"^\w{3}\s+\d{1,2}\s+\d{2}:\d{2}"  # Jan 15 12:30
)

# Pattern to detect log file format (timestamp at start of line)
# This will be updated from config
LOG_LINE_PATTERN = re.compile(DEFAULT_LOG_LINE_PATTERN)

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
        if "log" in path.name.lower() or "txt" in path.name.lower():
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


class MultiLogWatcher:
    """Watches multiple log directories and indexed files for errors."""

    def __init__(self, callback, error_patterns=None):
        self.callback = callback
        self.file_positions = {}
        self.file_error_counts = {}
        self.file_matched_lines = {}  # {filepath: deque of (line_num, line_text, timestamp, matched_patterns)}
        self.pattern_to_files = {}  # {pattern_str: set of filepaths that have matches}
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
        """Set the error patterns to match against.

        Args:
            patterns: List of pattern dicts with 'pattern' key, or strings
        """
        self.error_patterns = []
        self.pattern_strings = []  # Keep original pattern strings for tracking
        for p in patterns:
            # Handle both dict format and legacy string format
            if isinstance(p, dict):
                pattern_str = p.get("pattern", "")
            else:
                pattern_str = str(p)
            if pattern_str:
                if pattern_str.startswith("^"):
                    regex = re.compile(pattern_str, re.IGNORECASE)
                else:
                    regex = re.compile(re.escape(pattern_str), re.IGNORECASE)
                self.error_patterns.append(regex)
                self.pattern_strings.append(pattern_str)

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
        self.pattern_to_files.clear()

    def reset_file_count(self, filepath):
        """Reset error count and matched lines for a specific file."""
        if filepath in self.file_error_counts:
            self.file_error_counts[filepath] = 0
        if filepath in self.file_matched_lines:
            self.file_matched_lines[filepath].clear()
        # Remove this file from all pattern mappings
        for pattern_str in list(self.pattern_to_files.keys()):
            if filepath in self.pattern_to_files[pattern_str]:
                self.pattern_to_files[pattern_str].discard(filepath)
                if not self.pattern_to_files[pattern_str]:
                    del self.pattern_to_files[pattern_str]

    def get_matched_lines(self, filepath):
        """Get matched lines for a specific file."""
        return list(self.file_matched_lines.get(filepath, []))

    def get_files_for_pattern(self, pattern_str):
        """Get list of files that have at least one match for a specific pattern."""
        return sorted(list(self.pattern_to_files.get(pattern_str, set())))

    def _add_matched_line(self, filepath, line_num, line_text, line_timestamp=None, matched_patterns=None):
        """Add a matched line for a file."""
        if filepath not in self.file_matched_lines:
            self.file_matched_lines[filepath] = deque(maxlen=MAX_MATCHED_LINES_PER_FILE)
        matched_patterns = matched_patterns or []
        self.file_matched_lines[filepath].append((line_num, line_text.strip(), line_timestamp, matched_patterns))

        # Update pattern_to_files mapping
        for pattern_str in matched_patterns:
            if pattern_str not in self.pattern_to_files:
                self.pattern_to_files[pattern_str] = set()
            self.pattern_to_files[pattern_str].add(filepath)

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
        # Remove this file from pattern mappings (will be re-added during scan)
        for pattern_str in list(self.pattern_to_files.keys()):
            self.pattern_to_files[pattern_str].discard(file_key)

        # Read entire file to collect matched lines
        total_count = 0
        try:
            with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                line_num = 1
                for line in f:
                    match_count, matched_patterns = self._count_matches(line)
                    if match_count > 0:
                        line_timestamp = parse_log_timestamp(line)
                        if self._is_in_datetime_range(line_timestamp):
                            total_count += match_count
                            self._add_matched_line(file_key, line_num, line, line_timestamp, matched_patterns)
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
        # Remove this file from pattern mappings (will be re-added during scan)
        for pattern_str in list(self.pattern_to_files.keys()):
            self.pattern_to_files[pattern_str].discard(file_key)

        total_count = 0
        try:
            with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                line_num = 1
                for line in f:
                    match_count, matched_patterns = self._count_matches(line)
                    if match_count > 0:
                        line_timestamp = parse_log_timestamp(line)
                        if self._is_in_datetime_range(line_timestamp):
                            total_count += match_count
                            self._add_matched_line(file_key, line_num, line, line_timestamp, matched_patterns)
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

        # Import here to avoid issues when testing without watchdog
        try:
            from watchdog.observers import Observer
            from watchdog.events import FileSystemEventHandler

            class LogFileEventHandler(FileSystemEventHandler):
                def __init__(handler_self, watcher):
                    super().__init__()
                    handler_self.watcher = watcher

                def on_modified(handler_self, event):
                    if event.is_directory:
                        return
                    filepath = event.src_path
                    if handler_self.watcher._should_watch_file(filepath):
                        handler_self.watcher._check_file_immediate(filepath)

                def on_created(handler_self, event):
                    if event.is_directory:
                        return
                    filepath = event.src_path
                    if filepath.endswith('.log') and handler_self.watcher._should_watch_file(filepath):
                        handler_self.watcher._check_file_immediate(filepath)

            # Create observer and event handler
            self.observer = Observer()
            self.event_handler = LogFileEventHandler(self)

            # Schedule watches for all directories and file parent directories
            self._update_watches()

            # Start the observer
            self.observer.start()
        except ImportError:
            # Watchdog not available, fall back to polling
            self._start_polling()

    def _start_polling(self):
        """Fall back to polling if watchdog is not available."""
        self._poll_thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._poll_thread.start()

    def _poll_loop(self):
        """Polling loop for when FSEvents is not available."""
        while self.running:
            try:
                self._check_all_files()
            except Exception:
                pass
            threading.Event().wait(0.5)

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
            match_count, matched_patterns = self._count_matches(line)
            if match_count > 0:
                line_timestamp = parse_log_timestamp(line)
                if self._is_in_datetime_range(line_timestamp):
                    if file_key not in self.file_error_counts:
                        self.file_error_counts[file_key] = 0
                    self.file_error_counts[file_key] += match_count
                    self._add_matched_line(file_key, line_num, line, line_timestamp, matched_patterns)
                    self.callback(path.name, filepath, line_num, line.strip(), matched_patterns)
            line_num += 1

    def _count_matches(self, line):
        """Count how many patterns match a line and return matched pattern strings."""
        count = 0
        matched_patterns = []
        for i, pattern in enumerate(self.error_patterns):
            if pattern.search(line):
                count += 1
                matched_patterns.append(self.pattern_strings[i])
        return count, matched_patterns
