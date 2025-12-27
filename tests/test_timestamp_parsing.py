"""
Tests for timestamp parsing functionality.
"""

import sys
from pathlib import Path
from datetime import datetime

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from logwatch_core import (
    parse_log_timestamp,
    TIMESTAMP_PATTERNS,
    LOG_LINE_PATTERN,
)


class TestTimestampParsing:
    """Tests for parse_log_timestamp function."""

    def test_iso_format_with_space(self):
        """Test ISO format timestamp with space separator."""
        line = "2024-01-15 12:30:45 INFO Starting application"
        result = parse_log_timestamp(line)
        assert result is not None
        assert result == datetime(2024, 1, 15, 12, 30, 45)

    def test_iso_format_with_t_separator(self):
        """Test ISO format timestamp with T separator."""
        line = "2024-01-15T12:30:45 INFO Starting application"
        result = parse_log_timestamp(line)
        assert result is not None
        assert result == datetime(2024, 1, 15, 12, 30, 45)

    def test_iso_format_date_only(self):
        """Test ISO format with date only."""
        line = "2024-01-15 INFO Daily report"
        result = parse_log_timestamp(line)
        assert result is not None
        assert result == datetime(2024, 1, 15, 0, 0, 0)

    def test_us_format(self):
        """Test US format timestamp (MM-DD-YYYY HH:MM:SS)."""
        line = "01-15-2024 12:30:45 INFO Starting application"
        result = parse_log_timestamp(line)
        assert result is not None
        assert result == datetime(2024, 1, 15, 12, 30, 45)

    def test_bracketed_iso_format(self):
        """Test bracketed ISO format timestamp."""
        line = "[2024-01-15 12:30:45] INFO Starting application"
        result = parse_log_timestamp(line)
        assert result is not None
        assert result == datetime(2024, 1, 15, 12, 30, 45)

    def test_bracketed_iso_format_with_t(self):
        """Test bracketed ISO format with T separator."""
        line = "[2024-01-15T12:30:45] ERROR Something failed"
        result = parse_log_timestamp(line)
        assert result is not None
        assert result == datetime(2024, 1, 15, 12, 30, 45)

    def test_slash_separator(self):
        """Test date with slash separators."""
        line = "2024/01/15 12:30:45 DEBUG Processing"
        result = parse_log_timestamp(line)
        assert result is not None
        assert result == datetime(2024, 1, 15, 12, 30, 45)

    def test_no_timestamp(self):
        """Test line without timestamp."""
        line = "This is a plain text line without timestamp"
        result = parse_log_timestamp(line)
        assert result is None

    def test_invalid_timestamp(self):
        """Test line with invalid timestamp format."""
        line = "99-99-9999 99:99:99 Invalid"
        result = parse_log_timestamp(line)
        # Should return None due to ValueError in converter
        assert result is None

    def test_timestamp_in_middle_of_line(self):
        """Test timestamp appearing in middle of line."""
        line = "Some prefix 2024-01-15 12:30:45 INFO Message"
        result = parse_log_timestamp(line)
        assert result is not None
        assert result == datetime(2024, 1, 15, 12, 30, 45)

    def test_empty_line(self):
        """Test empty line."""
        result = parse_log_timestamp("")
        assert result is None

    def test_whitespace_only(self):
        """Test whitespace-only line."""
        result = parse_log_timestamp("   \t\n")
        assert result is None


class TestLogLinePattern:
    """Tests for LOG_LINE_PATTERN regex."""

    def test_iso_date_format(self):
        """Test ISO date format at start of line."""
        assert LOG_LINE_PATTERN.match("2024-01-15 INFO message")
        assert LOG_LINE_PATTERN.match("2024/01/15 INFO message")

    def test_us_date_format(self):
        """Test US date format at start of line."""
        assert LOG_LINE_PATTERN.match("01-15-2024 INFO message")
        assert LOG_LINE_PATTERN.match("01/15/2024 INFO message")

    def test_bracketed_date(self):
        """Test bracketed date format."""
        assert LOG_LINE_PATTERN.match("[2024-01-15 12:30:45] INFO message")

    def test_time_only(self):
        """Test time-only format."""
        assert LOG_LINE_PATTERN.match("12:30:45 INFO message")

    def test_syslog_format(self):
        """Test syslog-style format (Mon DD HH:MM)."""
        assert LOG_LINE_PATTERN.match("Jan 15 12:30 syslog message")
        assert LOG_LINE_PATTERN.match("Dec  5 08:00 syslog message")

    def test_no_match(self):
        """Test lines that shouldn't match log format."""
        assert not LOG_LINE_PATTERN.match("This is not a log line")
        assert not LOG_LINE_PATTERN.match("README.md content")


class TestTimestampEdgeCases:
    """Test edge cases for timestamp parsing."""

    def test_midnight(self):
        """Test midnight timestamp."""
        line = "2024-01-15 00:00:00 INFO Midnight event"
        result = parse_log_timestamp(line)
        assert result == datetime(2024, 1, 15, 0, 0, 0)

    def test_end_of_day(self):
        """Test end of day timestamp."""
        line = "2024-01-15 23:59:59 INFO End of day"
        result = parse_log_timestamp(line)
        assert result == datetime(2024, 1, 15, 23, 59, 59)

    def test_leap_year_date(self):
        """Test leap year date."""
        line = "2024-02-29 12:00:00 INFO Leap day"
        result = parse_log_timestamp(line)
        assert result == datetime(2024, 2, 29, 12, 0, 0)

    def test_year_boundary(self):
        """Test year boundary dates."""
        line1 = "2023-12-31 23:59:59 INFO Year end"
        line2 = "2024-01-01 00:00:00 INFO New year"

        result1 = parse_log_timestamp(line1)
        result2 = parse_log_timestamp(line2)

        assert result1 == datetime(2023, 12, 31, 23, 59, 59)
        assert result2 == datetime(2024, 1, 1, 0, 0, 0)

    def test_multiple_timestamps_in_line(self):
        """Test line with multiple timestamps - should match first valid one."""
        line = "2024-01-15 12:00:00 Retry at 2024-01-15 13:00:00"
        result = parse_log_timestamp(line)
        # Should match the first timestamp found
        assert result == datetime(2024, 1, 15, 12, 0, 0)
