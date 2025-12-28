"""
Tests for logfile pattern configuration and detection.
"""

import os
import sys
import json
import re
import tempfile
import shutil
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from logwatch_core import (
    DEFAULT_LOG_LINE_PATTERN,
    LOG_LINE_PATTERN,
)


class TestDefaultLogLinePattern:
    """Tests for default log line pattern."""

    def test_default_pattern_exists(self):
        """Test that default pattern is defined."""
        assert DEFAULT_LOG_LINE_PATTERN is not None
        assert len(DEFAULT_LOG_LINE_PATTERN) > 0

    def test_default_pattern_is_string(self):
        """Test that default pattern is a string."""
        assert isinstance(DEFAULT_LOG_LINE_PATTERN, str)

    def test_default_pattern_compiles(self):
        """Test that default pattern compiles as valid regex."""
        try:
            compiled = re.compile(DEFAULT_LOG_LINE_PATTERN)
            assert compiled is not None
        except re.error:
            pytest.fail("Default pattern should compile as valid regex")

    def test_log_line_pattern_initialized(self):
        """Test that LOG_LINE_PATTERN is initialized with default."""
        assert LOG_LINE_PATTERN is not None
        assert LOG_LINE_PATTERN.pattern == DEFAULT_LOG_LINE_PATTERN


class TestLogLinePatternMatching:
    """Tests for log line pattern matching."""

    @pytest.fixture
    def pattern(self):
        """Return a compiled pattern for testing."""
        return re.compile(DEFAULT_LOG_LINE_PATTERN)

    def test_matches_iso_date_format(self, pattern):
        """Test pattern matches ISO date format."""
        assert pattern.match("2024-01-15 10:00:01 INFO message")
        assert pattern.match("2024/01/15 10:00:01 INFO message")

    def test_matches_us_date_format(self, pattern):
        """Test pattern matches US date format."""
        assert pattern.match("01-15-2024 10:00:01 INFO message")
        assert pattern.match("01/15/2024 10:00:01 INFO message")

    def test_matches_bracketed_date(self, pattern):
        """Test pattern matches bracketed date format."""
        assert pattern.match("[2024-01-15 10:00:01] INFO message")
        assert pattern.match("[2024/01/15 10:00:01] ERROR message")

    def test_matches_time_only(self, pattern):
        """Test pattern matches time-only format."""
        assert pattern.match("10:00:01 INFO message")
        assert pattern.match("23:59:59 ERROR message")

    def test_matches_syslog_format(self, pattern):
        """Test pattern matches syslog date format."""
        assert pattern.match("Jan 15 10:00 syslog message")
        assert pattern.match("Dec  5 08:15 system message")

    def test_does_not_match_plain_text(self, pattern):
        """Test pattern does not match plain text."""
        assert not pattern.match("This is just plain text")
        assert not pattern.match("README.md content")
        assert not pattern.match("# Comment line")


class TestCustomLogLinePattern:
    """Tests for custom log line pattern configuration."""

    def test_custom_pattern_compilation(self):
        """Test that custom patterns can be compiled."""
        custom_pattern = r"^\[\w+\]"
        try:
            compiled = re.compile(custom_pattern)
            assert compiled is not None
            assert compiled.match("[ERROR] message")
            assert compiled.match("[INFO] message")
            assert not compiled.match("No bracket prefix")
        except re.error:
            pytest.fail("Custom pattern should compile successfully")

    def test_alternative_log_format(self):
        """Test pattern for alternative log format."""
        # Pattern for logs starting with level prefix
        custom_pattern = r"^(INFO|WARN|ERROR|DEBUG|CRITICAL)\s+"
        compiled = re.compile(custom_pattern)
        assert compiled.match("INFO This is a message")
        assert compiled.match("ERROR Something went wrong")
        assert not compiled.match("2024-01-15 INFO message")

    def test_java_log_format(self):
        """Test pattern for Java-style logs."""
        # Pattern for Java logs with fully qualified class names
        custom_pattern = r"^\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}\.\d{3}"
        compiled = re.compile(custom_pattern)
        assert compiled.match("2024-01-15 10:00:01.123 INFO message")
        assert compiled.match("2024-12-31 23:59:59.999 ERROR message")
        assert not compiled.match("2024-01-15 10:00:01 INFO message")


class TestLogLinePatternConfig:
    """Tests for log line pattern in configuration."""

    @pytest.fixture
    def temp_config_dir(self):
        """Create a temporary config directory."""
        tmp = tempfile.mkdtemp()
        config_dir = os.path.join(tmp, ".config", "logwatch-menubar")
        os.makedirs(config_dir, exist_ok=True)
        yield config_dir
        shutil.rmtree(tmp, ignore_errors=True)

    def test_config_with_custom_pattern(self, temp_config_dir):
        """Test configuration with custom log line pattern."""
        config_path = os.path.join(temp_config_dir, "config.json")
        custom_pattern = r"^\[\w+\]"
        config = {
            "directories": ["/var/log"],
            "sound_enabled": True,
            "log_line_pattern": custom_pattern
        }

        with open(config_path, "w") as f:
            json.dump(config, f)

        with open(config_path, "r") as f:
            loaded = json.load(f)

        assert "log_line_pattern" in loaded
        assert loaded["log_line_pattern"] == custom_pattern

    def test_config_without_custom_pattern(self, temp_config_dir):
        """Test configuration without custom pattern uses default."""
        config_path = os.path.join(temp_config_dir, "config.json")
        config = {
            "directories": ["/var/log"],
            "sound_enabled": True
        }

        with open(config_path, "w") as f:
            json.dump(config, f)

        with open(config_path, "r") as f:
            loaded = json.load(f)

        # Should not have log_line_pattern key, will use default
        assert "log_line_pattern" not in loaded

    def test_invalid_regex_pattern_in_config(self, temp_config_dir):
        """Test that invalid regex patterns are handled gracefully."""
        config_path = os.path.join(temp_config_dir, "config.json")
        # Invalid regex with unterminated group
        invalid_pattern = r"^(unclosed"
        config = {
            "directories": ["/var/log"],
            "log_line_pattern": invalid_pattern
        }

        with open(config_path, "w") as f:
            json.dump(config, f)

        with open(config_path, "r") as f:
            loaded = json.load(f)

        # Config loads, but pattern compilation should fail
        assert loaded["log_line_pattern"] == invalid_pattern
        with pytest.raises(re.error):
            re.compile(invalid_pattern)


class TestLogFileIdentification:
    """Tests for identifying log files using the pattern."""

    @pytest.fixture
    def temp_dir(self):
        """Create temporary directory with test files."""
        tmp = tempfile.mkdtemp()
        yield tmp
        shutil.rmtree(tmp, ignore_errors=True)

    def test_identify_log_file_by_content(self, temp_dir):
        """Test identifying log files by content matching pattern."""
        # Create a file with log-like content
        log_file = os.path.join(temp_dir, "app.log")
        with open(log_file, "w") as f:
            f.write("2024-01-15 10:00:01 INFO Starting application\n")
            f.write("2024-01-15 10:00:02 DEBUG Loading configuration\n")
            f.write("2024-01-15 10:00:03 ERROR Failed to connect\n")

        # Check if first line matches pattern
        pattern = re.compile(DEFAULT_LOG_LINE_PATTERN)
        with open(log_file, "r") as f:
            first_line = f.readline().strip()
            assert pattern.match(first_line)

    def test_identify_non_log_file(self, temp_dir):
        """Test that non-log files are not identified as logs."""
        # Create a regular text file
        text_file = os.path.join(temp_dir, "readme.txt")
        with open(text_file, "w") as f:
            f.write("This is a readme file\n")
            f.write("It contains plain text\n")
            f.write("Not log entries\n")

        pattern = re.compile(DEFAULT_LOG_LINE_PATTERN)
        with open(text_file, "r") as f:
            first_line = f.readline().strip()
            assert not pattern.match(first_line)

    def test_identify_mixed_content_file(self, temp_dir):
        """Test file with some log lines and some non-log lines."""
        mixed_file = os.path.join(temp_dir, "mixed.txt")
        with open(mixed_file, "w") as f:
            f.write("Some header text\n")
            f.write("2024-01-15 10:00:01 INFO This is a log line\n")
            f.write("More plain text\n")

        pattern = re.compile(DEFAULT_LOG_LINE_PATTERN)
        with open(mixed_file, "r") as f:
            lines = f.readlines()
            # First line should not match
            assert not pattern.match(lines[0].strip())
            # Second line should match
            assert pattern.match(lines[1].strip())
            # Third line should not match
            assert not pattern.match(lines[2].strip())
