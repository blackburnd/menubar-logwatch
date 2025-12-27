"""
Tests for MultiLogWatcher class functionality.
"""

import os
import sys
import time
import tempfile
import shutil
from pathlib import Path
from datetime import datetime

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from logwatch_core import MultiLogWatcher

MultiLogWatcher_class = MultiLogWatcher


class TestMultiLogWatcherLifecycle:
    """Tests for MultiLogWatcher lifecycle management."""

    def test_initialization(self):
        """Test watcher initializes correctly."""
        callback_calls = []
        watcher = MultiLogWatcher_class(callback=lambda *args: callback_calls.append(args))

        assert watcher.running is False
        assert watcher.observer is None
        assert len(watcher.error_patterns) > 0  # Default patterns

    def test_start_and_stop(self):
        """Test starting and stopping the watcher."""
        watcher = MultiLogWatcher_class(callback=lambda *args: None)

        watcher.start()
        assert watcher.running is True
        # observer may or may not be set depending on watchdog availability

        watcher.stop()
        assert watcher.running is False

    def test_start_only_once(self):
        """Test that starting when already running does nothing."""
        watcher = MultiLogWatcher_class(callback=lambda *args: None)

        watcher.start()
        was_running = watcher.running

        watcher.start()  # Try starting again
        assert watcher.running == was_running  # Still running, no change

        watcher.stop()


class TestMultiLogWatcherDirectories:
    """Tests for directory management."""

    def test_set_directories(self):
        """Test setting directories to watch."""
        watcher = MultiLogWatcher_class(callback=lambda *args: None)

        watcher.set_directories(["/path/to/logs", "/another/path"])

        assert "/path/to/logs" in watcher.watch_dirs
        assert "/another/path" in watcher.watch_dirs

    def test_set_directories_replaces(self):
        """Test that set_directories replaces existing list."""
        watcher = MultiLogWatcher_class(callback=lambda *args: None)

        watcher.set_directories(["/old/path"])
        watcher.set_directories(["/new/path"])

        assert "/old/path" not in watcher.watch_dirs
        assert "/new/path" in watcher.watch_dirs


class TestMultiLogWatcherIndexedFiles:
    """Tests for indexed file management."""

    def test_set_indexed_files(self):
        """Test setting indexed files."""
        watcher = MultiLogWatcher_class(callback=lambda *args: None)

        watcher.set_indexed_files(["/path/to/file1.log", "/path/to/file2.log"])

        assert "/path/to/file1.log" in watcher.watch_files
        assert "/path/to/file2.log" in watcher.watch_files

    def test_add_indexed_file(self):
        """Test adding a single indexed file."""
        watcher = MultiLogWatcher_class(callback=lambda *args: None)

        watcher.set_indexed_files(["/file1.log"])
        watcher.add_indexed_file("/file2.log")

        assert "/file1.log" in watcher.watch_files
        assert "/file2.log" in watcher.watch_files


class TestMultiLogWatcherErrorCounting:
    """Tests for error counting functionality."""

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory."""
        tmp = tempfile.mkdtemp()
        yield tmp
        shutil.rmtree(tmp, ignore_errors=True)

    def test_get_error_count(self):
        """Test getting error count for a file."""
        watcher = MultiLogWatcher_class(callback=lambda *args: None)

        watcher.file_error_counts["/file.log"] = 5
        assert watcher.get_error_count("/file.log") == 5

    def test_get_error_count_unknown_file(self):
        """Test getting error count for unknown file returns 0."""
        watcher = MultiLogWatcher_class(callback=lambda *args: None)

        assert watcher.get_error_count("/unknown.log") == 0

    def test_get_total_error_count(self):
        """Test getting total error count across all files."""
        watcher = MultiLogWatcher_class(callback=lambda *args: None)

        watcher.file_error_counts["/file1.log"] = 3
        watcher.file_error_counts["/file2.log"] = 7

        assert watcher.get_total_error_count() == 10

    def test_reset_counts(self):
        """Test resetting all error counts."""
        watcher = MultiLogWatcher_class(callback=lambda *args: None)

        watcher.file_error_counts["/file1.log"] = 3
        watcher.file_error_counts["/file2.log"] = 7

        watcher.reset_counts()

        assert watcher.get_total_error_count() == 0

    def test_reset_file_count(self):
        """Test resetting error count for specific file."""
        watcher = MultiLogWatcher_class(callback=lambda *args: None)

        watcher.file_error_counts["/file1.log"] = 3
        watcher.file_error_counts["/file2.log"] = 7

        watcher.reset_file_count("/file1.log")

        assert watcher.get_error_count("/file1.log") == 0
        assert watcher.get_error_count("/file2.log") == 7


class TestMultiLogWatcherFileState:
    """Tests for file state persistence."""

    def test_get_file_state(self):
        """Test exporting file state."""
        watcher = MultiLogWatcher_class(callback=lambda *args: None)

        watcher.file_positions["/file.log"] = (1000, 1700000000.0)
        watcher.file_error_counts["/file.log"] = 5

        state = watcher.get_file_state()

        assert "/file.log" in state
        assert state["/file.log"]["position"] == 1000
        assert state["/file.log"]["mtime"] == 1700000000.0
        assert state["/file.log"]["error_count"] == 5

    def test_restore_file_state(self):
        """Test restoring file state."""
        watcher = MultiLogWatcher_class(callback=lambda *args: None)

        state = {
            "/file.log": {
                "position": 1000,
                "mtime": 1700000000.0,
                "error_count": 5
            }
        }

        watcher.restore_file_state(state)

        assert watcher.file_positions["/file.log"] == (1000, 1700000000.0)
        assert watcher.file_error_counts["/file.log"] == 5


class TestMultiLogWatcherFileChecking:
    """Tests for file change detection."""

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory."""
        tmp = tempfile.mkdtemp()
        yield tmp
        shutil.rmtree(tmp, ignore_errors=True)

    def test_check_new_file(self, temp_dir):
        """Test checking a new file."""
        callback_calls = []
        watcher = MultiLogWatcher_class(callback=lambda *args: callback_calls.append(args))

        log_file = os.path.join(temp_dir, "test.log")
        with open(log_file, "w") as f:
            f.write("2024-01-15 10:00:00 INFO Starting\n")

        watcher._check_file(log_file)

        # First check should set position but not report errors
        assert log_file in watcher.file_positions

    def test_check_file_with_new_content(self, temp_dir):
        """Test detecting new content in file."""
        callback_calls = []
        watcher = MultiLogWatcher_class(callback=lambda *args: callback_calls.append(args))

        log_file = os.path.join(temp_dir, "test.log")

        # Initial content
        with open(log_file, "w") as f:
            f.write("2024-01-15 10:00:00 INFO Starting\n")

        watcher._check_file(log_file)
        initial_calls = len(callback_calls)

        # Add error content
        time.sleep(0.1)  # Ensure mtime changes
        with open(log_file, "a") as f:
            f.write("2024-01-15 10:00:01 ERROR Something failed\n")

        watcher._check_file(log_file)

        # Should have detected the error
        assert len(callback_calls) > initial_calls

    def test_check_file_rotation(self, temp_dir):
        """Test detecting file rotation (truncation)."""
        callback_calls = []
        watcher = MultiLogWatcher_class(callback=lambda *args: callback_calls.append(args))

        log_file = os.path.join(temp_dir, "test.log")

        # Initial large content
        with open(log_file, "w") as f:
            f.write("A" * 1000 + "\n")

        watcher._check_file(log_file)
        initial_pos = watcher.file_positions[log_file][0]
        assert initial_pos > 900  # Should be at end

        # Truncate file (rotation)
        time.sleep(0.1)
        with open(log_file, "w") as f:
            f.write("New content after rotation\n")

        watcher._check_file(log_file)

        # Position should be reset
        new_pos = watcher.file_positions[log_file][0]
        assert new_pos < initial_pos

    def test_check_nonexistent_file(self):
        """Test checking nonexistent file doesn't crash."""
        watcher = MultiLogWatcher_class(callback=lambda *args: None)

        # Should not raise
        watcher._check_file("/nonexistent/file.log")


class TestMultiLogWatcherReindexing:
    """Tests for file reindexing."""

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory."""
        tmp = tempfile.mkdtemp()
        yield tmp
        shutil.rmtree(tmp, ignore_errors=True)

    def test_count_errors_in_file(self, temp_dir):
        """Test counting errors in entire file."""
        watcher = MultiLogWatcher_class(callback=lambda *args: None)

        log_file = os.path.join(temp_dir, "test.log")
        with open(log_file, "w") as f:
            f.write("2024-01-15 10:00:00 INFO Starting\n")
            f.write("2024-01-15 10:00:01 ERROR First error\n")
            f.write("2024-01-15 10:00:02 DEBUG Debugging\n")
            f.write("2024-01-15 10:00:03 ERROR Second error\n")
            f.write("2024-01-15 10:00:04 CRITICAL Critical issue\n")

        watcher._count_errors_in_file(log_file)

        # Should count: 2 ERROR + 1 CRITICAL = 3 (from default patterns)
        assert watcher.get_error_count(log_file) >= 3

    def test_reindex_all_files(self, temp_dir):
        """Test reindexing all files."""
        watcher = MultiLogWatcher_class(callback=lambda *args: None)

        log_file = os.path.join(temp_dir, "test.log")
        with open(log_file, "w") as f:
            f.write("2024-01-15 10:00:00 ERROR An error\n")

        watcher.set_indexed_files([log_file])
        watcher.reindex_all_files()

        assert watcher.get_error_count(log_file) >= 1

    def test_reindex_with_progress_callback(self, temp_dir):
        """Test reindexing with progress callback."""
        progress_values = []
        watcher = MultiLogWatcher_class(callback=lambda *args: None)

        log_file = os.path.join(temp_dir, "test.log")
        with open(log_file, "w") as f:
            f.write("2024-01-15 10:00:00 ERROR An error\n")

        watcher.set_indexed_files([log_file])
        watcher.reindex_all_files(callback_progress=lambda x: progress_values.append(x))

        # Should have progress updates
        assert len(progress_values) > 0
        assert progress_values[-1] == 1.0  # Final progress should be 100%

    def test_reindex_with_datetime_filter(self, temp_dir):
        """Test reindexing with datetime filter."""
        watcher = MultiLogWatcher_class(callback=lambda *args: None)
        watcher.set_datetime_filter(
            start_dt=datetime(2024, 1, 15, 10, 0, 1),
            end_dt=datetime(2024, 1, 15, 10, 0, 3)
        )

        log_file = os.path.join(temp_dir, "test.log")
        with open(log_file, "w") as f:
            f.write("2024-01-15 10:00:00 ERROR Before range\n")
            f.write("2024-01-15 10:00:02 ERROR In range\n")
            f.write("2024-01-15 10:00:04 ERROR After range\n")

        watcher.set_indexed_files([log_file])
        watcher._count_errors_in_file(log_file)

        # Only the middle error should be counted
        assert watcher.get_error_count(log_file) == 1


class TestMultiLogWatcherWatchLoop:
    """Tests for the main watch loop."""

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory."""
        tmp = tempfile.mkdtemp()
        yield tmp
        shutil.rmtree(tmp, ignore_errors=True)

    def test_watch_loop_detects_changes(self, temp_dir):
        """Test that file checking detects changes."""
        callback_calls = []
        watcher = MultiLogWatcher_class(callback=lambda *args: callback_calls.append(args))

        log_file = os.path.join(temp_dir, "test.log")
        with open(log_file, "w") as f:
            f.write("2024-01-15 10:00:00 INFO Starting\n")

        watcher.set_indexed_files([log_file])

        # Initial check to set file position
        watcher._check_file(log_file)

        # Add an error
        with open(log_file, "a") as f:
            f.write("2024-01-15 10:00:01 ERROR New error\n")

        # Check again to detect the change
        watcher._check_file(log_file)

        # Should have detected the error
        assert len(callback_calls) > 0

    def test_watch_loop_handles_multiple_files(self, temp_dir):
        """Test watching multiple files."""
        callback_calls = []
        watcher = MultiLogWatcher_class(callback=lambda *args: callback_calls.append(args))

        log1 = os.path.join(temp_dir, "log1.log")
        log2 = os.path.join(temp_dir, "log2.log")

        with open(log1, "w") as f:
            f.write("Initial content\n")
        with open(log2, "w") as f:
            f.write("Initial content\n")

        watcher.set_indexed_files([log1, log2])

        # Initial check to set file positions
        watcher._check_file(log1)
        watcher._check_file(log2)

        # Add errors to both files
        with open(log1, "a") as f:
            f.write("2024-01-15 10:00:00 ERROR Error in log1\n")
        with open(log2, "a") as f:
            f.write("2024-01-15 10:00:00 ERROR Error in log2\n")

        # Check again to detect changes
        watcher._check_file(log1)
        watcher._check_file(log2)

        # Should have detected errors from both files
        assert len(callback_calls) >= 2


class TestMultiLogWatcherThreadSafety:
    """Tests for thread safety."""

    def test_directory_set_thread_safe(self):
        """Test that setting directories is thread-safe."""
        watcher = MultiLogWatcher_class(callback=lambda *args: None)
        watcher.start()

        # Should not raise
        for i in range(10):
            watcher.set_directories([f"/path{i}"])

        watcher.stop()

    def test_indexed_files_thread_safe(self):
        """Test that setting indexed files is thread-safe."""
        watcher = MultiLogWatcher_class(callback=lambda *args: None)
        watcher.start()

        # Should not raise
        for i in range(10):
            watcher.add_indexed_file(f"/file{i}.log")

        watcher.stop()
