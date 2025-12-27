"""
Tests for log file detection functionality.
"""

import os
import sys
import tempfile
import shutil
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

import unittest.mock as mock

# Mock the macOS-specific imports
with mock.patch.dict('sys.modules', {
    'rumps': mock.MagicMock(),
    'AppKit': mock.MagicMock(),
    'Foundation': mock.MagicMock(),
    'PyObjCTools': mock.MagicMock(),
    'PyObjCTools.AppHelper': mock.MagicMock(),
}):
    exec(open(Path(__file__).parent.parent / "logwatch-menubar.py").read())
    LogScanner_class = LogScanner
    LOG_LINE_PATTERN_re = LOG_LINE_PATTERN


class TestLogFileDetection:
    """Tests for log file detection in LogScanner."""

    @pytest.fixture
    def scanner(self):
        """Create a LogScanner instance."""
        return LogScanner_class(
            callback_found=lambda x: None,
            callback_done=lambda x: None,
            callback_progress=lambda x: None
        )

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory."""
        tmp = tempfile.mkdtemp()
        yield tmp
        shutil.rmtree(tmp, ignore_errors=True)

    def test_log_extension_detection(self, scanner, temp_dir):
        """Test detection of .log extension files."""
        log_file = os.path.join(temp_dir, "application.log")
        with open(log_file, "w") as f:
            f.write("Some content\n")

        assert scanner._is_log_file(log_file) is True

    def test_logs_extension_detection(self, scanner, temp_dir):
        """Test detection of .logs extension files."""
        log_file = os.path.join(temp_dir, "application.logs")
        with open(log_file, "w") as f:
            f.write("Some content\n")

        assert scanner._is_log_file(log_file) is True

    def test_log_in_filename(self, scanner, temp_dir):
        """Test detection of files with 'log' in name."""
        log_file = os.path.join(temp_dir, "mylog.txt")
        with open(log_file, "w") as f:
            f.write("2024-01-15 10:00:00 INFO Message\n")
            f.write("2024-01-15 10:00:01 DEBUG Another\n")
            f.write("2024-01-15 10:00:02 ERROR Problem\n")

        assert scanner._is_log_file(log_file) is True

    def test_non_log_file(self, scanner, temp_dir):
        """Test that non-log files are not detected."""
        txt_file = os.path.join(temp_dir, "readme.txt")
        with open(txt_file, "w") as f:
            f.write("This is just a text file\n")
            f.write("Without any log format\n")

        assert scanner._is_log_file(txt_file) is False

    def test_log_name_without_format(self, scanner, temp_dir):
        """Test file with 'log' in name but no log format."""
        log_file = os.path.join(temp_dir, "catalog.txt")
        with open(log_file, "w") as f:
            f.write("Item 1: Widget\n")
            f.write("Item 2: Gadget\n")
            f.write("Item 3: Thing\n")

        # 'log' is in 'catalog' but content doesn't have log format
        assert scanner._is_log_file(log_file) is False


class TestHasLogFormat:
    """Tests for _has_log_format method."""

    @pytest.fixture
    def scanner(self):
        """Create a LogScanner instance."""
        return LogScanner_class(
            callback_found=lambda x: None,
            callback_done=lambda x: None,
            callback_progress=lambda x: None
        )

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory."""
        tmp = tempfile.mkdtemp()
        yield tmp
        shutil.rmtree(tmp, ignore_errors=True)

    def test_valid_log_format(self, scanner, temp_dir):
        """Test file with valid log format."""
        log_file = os.path.join(temp_dir, "test.txt")
        with open(log_file, "w") as f:
            f.write("2024-01-15 10:00:00 INFO First line\n")
            f.write("2024-01-15 10:00:01 DEBUG Second line\n")
            f.write("2024-01-15 10:00:02 ERROR Third line\n")

        assert scanner._has_log_format(log_file) is True

    def test_mixed_format(self, scanner, temp_dir):
        """Test file with mixed log and non-log lines."""
        log_file = os.path.join(temp_dir, "test.txt")
        with open(log_file, "w") as f:
            f.write("2024-01-15 10:00:00 INFO Log line\n")
            f.write("Plain text line\n")
            f.write("2024-01-15 10:00:01 DEBUG Another log\n")
            f.write("More plain text\n")
            f.write("2024-01-15 10:00:02 ERROR Error log\n")

        # Should still pass as 3 of 5 lines match
        assert scanner._has_log_format(log_file) is True

    def test_insufficient_log_lines(self, scanner, temp_dir):
        """Test file with too few log-formatted lines."""
        log_file = os.path.join(temp_dir, "test.txt")
        with open(log_file, "w") as f:
            f.write("2024-01-15 10:00:00 INFO Only one log line\n")
            f.write("Plain text\n")
            f.write("More plain text\n")
            f.write("Even more plain text\n")
            f.write("Last plain text\n")

        # Only 1 of 5 lines match, needs at least 2
        assert scanner._has_log_format(log_file) is False

    def test_empty_file(self, scanner, temp_dir):
        """Test empty file."""
        log_file = os.path.join(temp_dir, "empty.txt")
        with open(log_file, "w") as f:
            pass  # Create empty file

        assert scanner._has_log_format(log_file) is False

    def test_empty_lines_skipped(self, scanner, temp_dir):
        """Test that empty lines are skipped in format check."""
        log_file = os.path.join(temp_dir, "test.txt")
        with open(log_file, "w") as f:
            f.write("\n")
            f.write("2024-01-15 10:00:00 INFO First\n")
            f.write("\n")
            f.write("2024-01-15 10:00:01 DEBUG Second\n")
            f.write("\n")

        # Empty lines skipped, only 2 lines checked, both match
        assert scanner._has_log_format(log_file) is True

    def test_nonexistent_file(self, scanner):
        """Test handling of nonexistent file."""
        assert scanner._has_log_format("/nonexistent/path/file.txt") is False

    def test_different_timestamp_formats(self, scanner, temp_dir):
        """Test recognition of different timestamp formats."""
        log_file = os.path.join(temp_dir, "test.txt")
        with open(log_file, "w") as f:
            f.write("2024-01-15 10:00:00 ISO format\n")
            f.write("[2024-01-15 10:00:01] Bracketed format\n")
            f.write("01-15-2024 10:00:02 US format\n")

        assert scanner._has_log_format(log_file) is True

    def test_syslog_format(self, scanner, temp_dir):
        """Test recognition of syslog format."""
        log_file = os.path.join(temp_dir, "syslog.txt")
        with open(log_file, "w") as f:
            f.write("Jan 15 10:00:00 hostname kernel: message\n")
            f.write("Jan 15 10:00:01 hostname sshd: login\n")
            f.write("Jan 15 10:00:02 hostname systemd: started\n")

        assert scanner._has_log_format(log_file) is True


class TestDirectoryExclusions:
    """Tests for directory exclusions during scanning."""

    @pytest.fixture
    def scanner(self):
        """Create a LogScanner instance with tracking."""
        found_files = []
        return LogScanner_class(
            callback_found=lambda x: found_files.append(x),
            callback_done=lambda x: None,
            callback_progress=lambda x: None
        ), found_files

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory."""
        tmp = tempfile.mkdtemp()
        yield tmp
        shutil.rmtree(tmp, ignore_errors=True)

    def test_skip_hidden_directories(self, scanner, temp_dir):
        """Test that hidden directories are skipped."""
        scanner_obj, found_files = scanner
        hidden_dir = os.path.join(temp_dir, ".hidden")
        os.makedirs(hidden_dir)
        log_file = os.path.join(hidden_dir, "hidden.log")
        with open(log_file, "w") as f:
            f.write("Log content\n")

        # Scan directly won't find files in hidden dirs
        scanner_obj._scan_directory(temp_dir)
        assert log_file not in found_files

    def test_skip_node_modules(self, scanner, temp_dir):
        """Test that node_modules is skipped."""
        scanner_obj, found_files = scanner
        node_dir = os.path.join(temp_dir, "node_modules")
        os.makedirs(node_dir)
        log_file = os.path.join(node_dir, "package.log")
        with open(log_file, "w") as f:
            f.write("Log content\n")

        scanner_obj._scan_directory(temp_dir)
        assert log_file not in found_files

    def test_skip_pycache(self, scanner, temp_dir):
        """Test that __pycache__ is skipped."""
        scanner_obj, found_files = scanner
        cache_dir = os.path.join(temp_dir, "__pycache__")
        os.makedirs(cache_dir)
        log_file = os.path.join(cache_dir, "cache.log")
        with open(log_file, "w") as f:
            f.write("Log content\n")

        scanner_obj._scan_directory(temp_dir)
        assert log_file not in found_files

    def test_skip_venv(self, scanner, temp_dir):
        """Test that venv is skipped."""
        scanner_obj, found_files = scanner
        venv_dir = os.path.join(temp_dir, "venv")
        os.makedirs(venv_dir)
        log_file = os.path.join(venv_dir, "pip.log")
        with open(log_file, "w") as f:
            f.write("Log content\n")

        scanner_obj._scan_directory(temp_dir)
        assert log_file not in found_files

    def test_skip_git(self, scanner, temp_dir):
        """Test that .git is skipped."""
        scanner_obj, found_files = scanner
        git_dir = os.path.join(temp_dir, ".git")
        os.makedirs(git_dir)
        log_file = os.path.join(git_dir, "git.log")
        with open(log_file, "w") as f:
            f.write("Log content\n")

        scanner_obj._scan_directory(temp_dir)
        assert log_file not in found_files

    def test_regular_subdirectory_scanned(self, scanner, temp_dir):
        """Test that regular subdirectories are scanned."""
        scanner_obj, found_files = scanner
        sub_dir = os.path.join(temp_dir, "logs")
        os.makedirs(sub_dir)
        log_file = os.path.join(sub_dir, "app.log")
        with open(log_file, "w") as f:
            f.write("Log content\n")

        # Set running to True so _scan_directory processes subdirs
        scanner_obj.running = True
        scanner_obj._scan_directory(temp_dir)
        assert log_file in found_files
