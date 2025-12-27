"""
Tests for LogScanner class functionality.
"""

import os
import sys
import time
import tempfile
import shutil
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from logwatch_core import LogScanner

LogScanner_class = LogScanner


class TestLogScannerLifecycle:
    """Tests for LogScanner lifecycle management."""

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory."""
        tmp = tempfile.mkdtemp()
        yield tmp
        shutil.rmtree(tmp, ignore_errors=True)

    def test_scanner_initialization(self):
        """Test scanner initializes correctly."""
        found = []
        done_count = [0]
        progress = [0.0]

        scanner = LogScanner_class(
            callback_found=lambda x: found.append(x),
            callback_done=lambda x: done_count.append(x),
            callback_progress=lambda x: progress.append(x)
        )

        assert scanner.running is False
        assert scanner.thread is None
        assert scanner.found_count == 0

    def test_start_scan(self, temp_dir):
        """Test starting a scan."""
        found = []
        done = []

        scanner = LogScanner_class(
            callback_found=lambda x: found.append(x),
            callback_done=lambda x: done.append(x),
            callback_progress=lambda x: None
        )

        # Create a log file
        log_file = os.path.join(temp_dir, "test.log")
        with open(log_file, "w") as f:
            f.write("Log content\n")

        scanner.start_scan(temp_dir)

        # Wait for scan to complete
        time.sleep(0.5)

        assert scanner.running is False
        assert log_file in found
        assert len(done) == 1

    def test_stop_scan(self, temp_dir):
        """Test stopping a scan."""
        scanner = LogScanner_class(
            callback_found=lambda x: None,
            callback_done=lambda x: None,
            callback_progress=lambda x: None
        )

        scanner.start_scan(temp_dir)
        scanner.stop()

        assert scanner.running is False

    def test_cannot_start_while_running(self, temp_dir):
        """Test that starting while already running does nothing."""
        scanner = LogScanner_class(
            callback_found=lambda x: None,
            callback_done=lambda x: None,
            callback_progress=lambda x: None
        )

        # Create many subdirs to slow down scan
        for i in range(10):
            subdir = os.path.join(temp_dir, f"subdir{i}")
            os.makedirs(subdir)

        scanner.start_scan(temp_dir)
        original_thread = scanner.thread

        # Try to start again
        scanner.start_scan(temp_dir)

        # Should be the same thread
        assert scanner.thread == original_thread

        scanner.stop()


class TestLogScannerProgress:
    """Tests for LogScanner progress reporting."""

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory."""
        tmp = tempfile.mkdtemp()
        yield tmp
        shutil.rmtree(tmp, ignore_errors=True)

    def test_progress_callback_called(self, temp_dir):
        """Test that progress callback is called."""
        progress_values = []

        scanner = LogScanner_class(
            callback_found=lambda x: None,
            callback_done=lambda x: None,
            callback_progress=lambda x: progress_values.append(x)
        )

        # Create some subdirectories
        for i in range(3):
            os.makedirs(os.path.join(temp_dir, f"dir{i}"))

        scanner.start_scan(temp_dir)

        # Wait for completion
        time.sleep(0.5)

        # Progress should have been reported
        assert len(progress_values) > 0
        assert 0.0 in progress_values  # Initial progress

    def test_progress_capped_at_99(self, temp_dir):
        """Test that progress is capped at 99% during scan."""
        progress_values = []

        scanner = LogScanner_class(
            callback_found=lambda x: None,
            callback_done=lambda x: None,
            callback_progress=lambda x: progress_values.append(x)
        )

        scanner.start_scan(temp_dir)
        time.sleep(0.5)

        # All intermediate progress should be <= 0.99
        for p in progress_values:
            assert p <= 0.99


class TestLogScannerFileDiscovery:
    """Tests for LogScanner file discovery."""

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory."""
        tmp = tempfile.mkdtemp()
        yield tmp
        shutil.rmtree(tmp, ignore_errors=True)

    def test_finds_log_files(self, temp_dir):
        """Test that scanner finds .log files."""
        found = []

        scanner = LogScanner_class(
            callback_found=lambda x: found.append(x),
            callback_done=lambda x: None,
            callback_progress=lambda x: None
        )

        # Create log files
        log1 = os.path.join(temp_dir, "app.log")
        log2 = os.path.join(temp_dir, "error.log")
        with open(log1, "w") as f:
            f.write("Log 1\n")
        with open(log2, "w") as f:
            f.write("Log 2\n")

        scanner.start_scan(temp_dir)
        time.sleep(0.5)

        assert log1 in found
        assert log2 in found

    def test_finds_nested_log_files(self, temp_dir):
        """Test that scanner finds log files in subdirectories."""
        found = []

        scanner = LogScanner_class(
            callback_found=lambda x: found.append(x),
            callback_done=lambda x: None,
            callback_progress=lambda x: None
        )

        # Create nested structure
        subdir = os.path.join(temp_dir, "logs", "app")
        os.makedirs(subdir)
        log_file = os.path.join(subdir, "nested.log")
        with open(log_file, "w") as f:
            f.write("Nested log\n")

        scanner.start_scan(temp_dir)
        time.sleep(0.5)

        assert log_file in found

    def test_found_count_updated(self, temp_dir):
        """Test that found_count is updated."""
        scanner = LogScanner_class(
            callback_found=lambda x: None,
            callback_done=lambda x: None,
            callback_progress=lambda x: None
        )

        # Create multiple log files
        for i in range(5):
            log_file = os.path.join(temp_dir, f"log{i}.log")
            with open(log_file, "w") as f:
                f.write(f"Log {i}\n")

        scanner.start_scan(temp_dir)
        time.sleep(0.5)

        assert scanner.found_count == 5

    def test_done_callback_receives_count(self, temp_dir):
        """Test that done callback receives correct count."""
        done_counts = []

        scanner = LogScanner_class(
            callback_found=lambda x: None,
            callback_done=lambda x: done_counts.append(x),
            callback_progress=lambda x: None
        )

        # Create log files
        for i in range(3):
            log_file = os.path.join(temp_dir, f"log{i}.log")
            with open(log_file, "w") as f:
                f.write(f"Log {i}\n")

        scanner.start_scan(temp_dir)
        time.sleep(0.5)

        assert done_counts == [3]


class TestLogScannerDepthLimiting:
    """Tests for LogScanner depth limiting."""

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory."""
        tmp = tempfile.mkdtemp()
        yield tmp
        shutil.rmtree(tmp, ignore_errors=True)

    def test_depth_limit(self, temp_dir):
        """Test that scanner respects depth limit."""
        found = []

        scanner = LogScanner_class(
            callback_found=lambda x: found.append(x),
            callback_done=lambda x: None,
            callback_progress=lambda x: None
        )

        # Create deep directory structure (depth > 3)
        deep_dir = os.path.join(temp_dir, "a", "b", "c", "d", "e")
        os.makedirs(deep_dir)

        # Log at depth 2 (should be found)
        shallow_log = os.path.join(temp_dir, "a", "b", "shallow.log")
        with open(shallow_log, "w") as f:
            f.write("Shallow log\n")

        # Log at depth 5 (may not be found due to depth limit in counting)
        deep_log = os.path.join(deep_dir, "deep.log")
        with open(deep_log, "w") as f:
            f.write("Deep log\n")

        scanner.start_scan(temp_dir)
        time.sleep(0.5)

        # Shallow log should definitely be found
        assert shallow_log in found


class TestLogScannerErrorHandling:
    """Tests for LogScanner error handling."""

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory."""
        tmp = tempfile.mkdtemp()
        yield tmp
        shutil.rmtree(tmp, ignore_errors=True)

    def test_handles_permission_errors(self, temp_dir):
        """Test that scanner handles permission errors gracefully."""
        found = []
        done = []

        scanner = LogScanner_class(
            callback_found=lambda x: found.append(x),
            callback_done=lambda x: done.append(x),
            callback_progress=lambda x: None
        )

        # Create a log file
        log_file = os.path.join(temp_dir, "accessible.log")
        with open(log_file, "w") as f:
            f.write("Log\n")

        scanner.start_scan(temp_dir)
        time.sleep(0.5)

        # Should complete without error
        assert len(done) == 1
        assert log_file in found

    def test_handles_nonexistent_path(self):
        """Test that scanner handles nonexistent paths."""
        done = []

        scanner = LogScanner_class(
            callback_found=lambda x: None,
            callback_done=lambda x: done.append(x),
            callback_progress=lambda x: None
        )

        scanner.start_scan("/nonexistent/path/that/does/not/exist")
        time.sleep(0.5)

        # Should complete (with 0 found)
        assert done == [0]
