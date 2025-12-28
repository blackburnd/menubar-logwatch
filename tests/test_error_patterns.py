"""
Tests for error pattern matching functionality.
"""

import os
import sys
import re
import tempfile
import shutil
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from logwatch_core import (
    MultiLogWatcher,
    DEFAULT_ERROR_PATTERNS,
)


class TestErrorPatternMatching:
    """Tests for error pattern matching in MultiLogWatcher."""

    @pytest.fixture
    def watcher(self):
        """Create a MultiLogWatcher instance."""
        return MultiLogWatcher(callback=lambda *args: None)

    def test_default_patterns(self, watcher):
        """Test that default patterns are set correctly."""
        expected = ["exception", "error", "traceback", "failed", "critical"]
        # Check that patterns are compiled regexes
        assert len(watcher.error_patterns) == len(expected)
        for pattern in watcher.error_patterns:
            assert isinstance(pattern, re.Pattern)

    def test_count_matches_single_pattern(self, watcher):
        """Test counting matches with single pattern."""
        watcher.set_error_patterns(["error"])
        count, patterns = watcher._count_matches("ERROR: Something went wrong")
        assert count == 1
        count, patterns = watcher._count_matches("No problems here")
        assert count == 0

    def test_count_matches_multiple_patterns(self, watcher):
        """Test counting with multiple patterns matching."""
        watcher.set_error_patterns(["error", "failed"])
        # Both patterns match
        line = "ERROR: Connection failed to server"
        count, patterns = watcher._count_matches(line)

        assert count == 2

    def test_case_insensitive_matching(self, watcher):
        """Test that matching is case insensitive."""
        watcher.set_error_patterns(["error"])
        count, patterns = watcher._count_matches("ERROR: uppercase")

        assert count == 1
        count, patterns = watcher._count_matches("error: lowercase")

        assert count == 1
        count, patterns = watcher._count_matches("Error: mixed case")

        assert count == 1
        count, patterns = watcher._count_matches("eRrOr: weird case")

        assert count == 1

    def test_regex_pattern(self, watcher):
        """Test regex patterns (starting with ^)."""
        watcher.set_error_patterns(["^ERROR.*timeout"])
        count, patterns = watcher._count_matches("ERROR: Connection timeout")

        assert count == 1
        count, patterns = watcher._count_matches("ERROR: timeout occurred")

        assert count == 1
        count, patterns = watcher._count_matches("WARNING: Connection timeout")

        assert count == 0

    def test_escaped_special_chars(self, watcher):
        """Test that special regex chars are escaped for literal patterns."""
        watcher.set_error_patterns(["[ERROR]"])
        # Should match literal [ERROR] not regex character class
        count, patterns = watcher._count_matches("[ERROR] Something happened")

        assert count == 1
        count, patterns = watcher._count_matches("ERROR Something happened")

        assert count == 0

    def test_empty_pattern_list(self, watcher):
        """Test with empty pattern list."""
        watcher.set_error_patterns([])
        count, patterns = watcher._count_matches("ERROR: This should not match")

        assert count == 0

    def test_pattern_in_middle_of_line(self, watcher):
        """Test pattern matching in middle of line."""
        watcher.set_error_patterns(["error"])
        count, patterns = watcher._count_matches("2024-01-15 ERROR: message")

        assert count == 1
        count, patterns = watcher._count_matches("This error occurred")

        assert count == 1

    def test_multiple_occurrences_same_pattern(self, watcher):
        """Test that multiple occurrences of same pattern count as 1."""
        watcher.set_error_patterns(["error"])
        # Pattern matches once per pattern, not per occurrence
        line = "error error error"
        count, patterns = watcher._count_matches(line)

        assert count == 1

    def test_common_error_patterns(self, watcher):
        """Test matching common error patterns."""
        # Use default patterns
        test_cases = [
            ("NullPointerException at line 42", True),
            ("java.lang.Exception: File not found", True),
            ("Traceback (most recent call last):", True),
            ("ERROR: Database connection failed", True),
            ("CRITICAL: System out of memory", True),
            ("INFO: Application started successfully", False),
            ("DEBUG: Processing request", False),
        ]

        for line, should_match in test_cases:
            count, patterns = watcher._count_matches(line)
            if should_match:
                assert count > 0, f"Expected match for: {line}"
            else:
                assert count == 0, f"Expected no match for: {line}"


class TestPatternSetting:
    """Tests for setting error patterns."""

    def test_set_patterns_replaces_existing(self):
        """Test that set_error_patterns replaces existing patterns."""
        watcher = MultiLogWatcher(callback=lambda *args: None)
        watcher.set_error_patterns(["pattern1"])
        assert len(watcher.error_patterns) == 1

        watcher.set_error_patterns(["new1", "new2"])
        assert len(watcher.error_patterns) == 2

    def test_patterns_compiled_as_regex(self):
        """Test that patterns are compiled as regex objects."""
        watcher = MultiLogWatcher(callback=lambda *args: None)
        watcher.set_error_patterns(["error", "^WARNING.*"])

        for pattern in watcher.error_patterns:
            assert isinstance(pattern, re.Pattern)

    def test_regex_pattern_preserved(self):
        """Test that regex patterns starting with ^ are not escaped."""
        watcher = MultiLogWatcher(callback=lambda *args: None)
        watcher.set_error_patterns(["^ERROR\\s+\\d+"])

        # Should match regex pattern
        count, patterns = watcher._count_matches("ERROR 123 message")

        assert count == 1
        count, patterns = watcher._count_matches("WARNING 123 message")

        assert count == 0


class TestDatetimeFiltering:
    """Tests for datetime range filtering."""

    @pytest.fixture
    def watcher(self):
        """Create a MultiLogWatcher instance."""
        return MultiLogWatcher(callback=lambda *args: None)

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory."""
        tmp = tempfile.mkdtemp()
        yield tmp
        shutil.rmtree(tmp, ignore_errors=True)

    def test_no_filter_includes_all(self, watcher):
        """Test that no filter includes all timestamps."""
        from datetime import datetime as dt
        watcher.set_datetime_filter(None, None)

        # All should be included
        assert watcher._is_in_datetime_range(dt(2024, 1, 15)) is True
        assert watcher._is_in_datetime_range(dt(2020, 1, 1)) is True
        assert watcher._is_in_datetime_range(None) is True

    def test_start_filter(self, watcher):
        """Test start datetime filter."""
        from datetime import datetime as dt
        watcher.set_datetime_filter(start_dt=dt(2024, 1, 15))

        assert watcher._is_in_datetime_range(dt(2024, 1, 15)) is True
        assert watcher._is_in_datetime_range(dt(2024, 1, 16)) is True
        assert watcher._is_in_datetime_range(dt(2024, 1, 14)) is False

    def test_end_filter(self, watcher):
        """Test end datetime filter."""
        from datetime import datetime as dt
        watcher.set_datetime_filter(end_dt=dt(2024, 1, 15))

        assert watcher._is_in_datetime_range(dt(2024, 1, 15)) is True
        assert watcher._is_in_datetime_range(dt(2024, 1, 14)) is True
        assert watcher._is_in_datetime_range(dt(2024, 1, 16)) is False

    def test_range_filter(self, watcher):
        """Test both start and end datetime filter."""
        from datetime import datetime as dt
        watcher.set_datetime_filter(
            start_dt=dt(2024, 1, 10),
            end_dt=dt(2024, 1, 20)
        )

        assert watcher._is_in_datetime_range(dt(2024, 1, 15)) is True
        assert watcher._is_in_datetime_range(dt(2024, 1, 10)) is True
        assert watcher._is_in_datetime_range(dt(2024, 1, 20)) is True
        assert watcher._is_in_datetime_range(dt(2024, 1, 9)) is False
        assert watcher._is_in_datetime_range(dt(2024, 1, 21)) is False

    def test_none_timestamp_included(self, watcher):
        """Test that None timestamp (unparseable) is included by default."""
        from datetime import datetime as dt
        watcher.set_datetime_filter(
            start_dt=dt(2024, 1, 10),
            end_dt=dt(2024, 1, 20)
        )

        # Lines without parseable timestamps should be included
        assert watcher._is_in_datetime_range(None) is True


class TestMatchedLinesStorage:
    """Tests for storing matched lines."""

    @pytest.fixture
    def watcher(self):
        """Create a MultiLogWatcher instance."""
        return MultiLogWatcher(callback=lambda *args: None)

    def test_add_matched_line(self, watcher):
        """Test adding a matched line."""
        from datetime import datetime as dt
        watcher._add_matched_line(
            "/path/to/file.log",
            10,
            "ERROR: Something went wrong",
            dt(2024, 1, 15, 12, 0, 0)
        )

        lines = watcher.get_matched_lines("/path/to/file.log")
        assert len(lines) == 1
        assert lines[0][0] == 10  # line number
        assert lines[0][1] == "ERROR: Something went wrong"  # text (stripped)

    def test_max_matched_lines(self, watcher):
        """Test that matched lines are limited."""
        filepath = "/path/to/file.log"

        # Add more than MAX_MATCHED_LINES_PER_FILE
        for i in range(60):
            watcher._add_matched_line(filepath, i, f"Error {i}")

        lines = watcher.get_matched_lines(filepath)
        # Should be limited to MAX_MATCHED_LINES_PER_FILE (50)
        assert len(lines) == 50

        # Should have the most recent lines (deque behavior)
        assert lines[-1][0] == 59
        assert lines[0][0] == 10  # First 10 were pushed out

    def test_get_matched_lines_empty(self, watcher):
        """Test getting matched lines for file with no matches."""
        lines = watcher.get_matched_lines("/nonexistent/file.log")
        assert lines == []

    def test_reset_file_count_clears_matches(self, watcher):
        """Test that reset_file_count clears matched lines."""
        filepath = "/path/to/file.log"
        watcher._add_matched_line(filepath, 1, "Error 1")
        watcher._add_matched_line(filepath, 2, "Error 2")
        watcher.file_error_counts[filepath] = 2

        watcher.reset_file_count(filepath)

        assert watcher.get_error_count(filepath) == 0
        assert watcher.get_matched_lines(filepath) == []

    def test_reset_counts_clears_all(self, watcher):
        """Test that reset_counts clears all files."""
        watcher._add_matched_line("/file1.log", 1, "Error 1")
        watcher._add_matched_line("/file2.log", 1, "Error 2")
        watcher.file_error_counts["/file1.log"] = 1
        watcher.file_error_counts["/file2.log"] = 1

        watcher.reset_counts()

        assert watcher.get_total_error_count() == 0
        assert watcher.get_matched_lines("/file1.log") == []
        assert watcher.get_matched_lines("/file2.log") == []
