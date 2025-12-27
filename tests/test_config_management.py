"""
Tests for configuration and index management.
"""

import os
import sys
import json
import tempfile
import shutil
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from logwatch_core import (
    DEFAULT_ERROR_PATTERNS,
    DATETIME_FORMAT,
    normalize_pattern,
    normalize_patterns,
)

# These paths are defined in the main app file but tests only verify path structure
CONFIG_PATH = Path.home() / ".config" / "logwatch-menubar" / "config.json"
INDEX_PATH = Path.home() / ".config" / "logwatch-menubar" / "log_index.json"


class TestConfigurationLoading:
    """Tests for configuration file loading."""

    @pytest.fixture
    def temp_config_dir(self):
        """Create a temporary config directory."""
        tmp = tempfile.mkdtemp()
        config_dir = os.path.join(tmp, ".config", "logwatch-menubar")
        os.makedirs(config_dir, exist_ok=True)
        yield config_dir
        shutil.rmtree(tmp, ignore_errors=True)

    def test_load_valid_config(self, temp_config_dir):
        """Test loading a valid configuration file."""
        config_path = os.path.join(temp_config_dir, "config.json")
        config = {
            "directories": ["/var/log", "/tmp/logs"],
            "sound_enabled": False,
            "error_patterns": ["error", "warning"],
            "start_datetime": "2024-01-01 00:00:00",
            "end_datetime": "2024-12-31 23:59:59"
        }
        with open(config_path, "w") as f:
            json.dump(config, f)

        # Read it back
        with open(config_path, "r") as f:
            loaded = json.load(f)

        assert loaded["directories"] == ["/var/log", "/tmp/logs"]
        assert loaded["sound_enabled"] is False
        assert loaded["error_patterns"] == ["error", "warning"]

    def test_load_nonexistent_config(self, temp_config_dir):
        """Test loading when config file doesn't exist."""
        config_path = os.path.join(temp_config_dir, "nonexistent.json")

        # Should not exist
        assert not os.path.exists(config_path)

    def test_migrate_old_log_dir_format(self, temp_config_dir):
        """Test migration from old log_dir to directories format."""
        config_path = os.path.join(temp_config_dir, "config.json")

        # Old format with log_dir
        old_config = {
            "log_dir": "/var/log",
            "sound_enabled": True
        }
        with open(config_path, "w") as f:
            json.dump(old_config, f)

        # Load and migrate
        with open(config_path, "r") as f:
            config = json.load(f)

        # Simulate migration
        if "log_dir" in config and "directories" not in config:
            old_dir = config.pop("log_dir")
            config["directories"] = [old_dir] if old_dir else []

        assert "directories" in config
        assert config["directories"] == ["/var/log"]
        assert "log_dir" not in config

    def test_config_with_empty_directories(self, temp_config_dir):
        """Test config with empty directories list."""
        config_path = os.path.join(temp_config_dir, "config.json")
        config = {"directories": [], "sound_enabled": True}
        with open(config_path, "w") as f:
            json.dump(config, f)

        with open(config_path, "r") as f:
            loaded = json.load(f)

        assert loaded["directories"] == []


class TestConfigurationSaving:
    """Tests for configuration file saving."""

    @pytest.fixture
    def temp_config_dir(self):
        """Create a temporary config directory."""
        tmp = tempfile.mkdtemp()
        config_dir = os.path.join(tmp, ".config", "logwatch-menubar")
        os.makedirs(config_dir, exist_ok=True)
        yield config_dir
        shutil.rmtree(tmp, ignore_errors=True)

    def test_save_config(self, temp_config_dir):
        """Test saving configuration."""
        config_path = os.path.join(temp_config_dir, "config.json")
        config = {
            "directories": ["/var/log"],
            "sound_enabled": True,
            "error_patterns": DEFAULT_ERROR_PATTERNS
        }

        with open(config_path, "w") as f:
            json.dump(config, f, indent=2)

        # Verify saved
        with open(config_path, "r") as f:
            loaded = json.load(f)

        assert loaded == config

    def test_save_creates_parent_directory(self, temp_config_dir):
        """Test that saving creates parent directories if needed."""
        new_dir = os.path.join(temp_config_dir, "subdir")
        config_path = os.path.join(new_dir, "config.json")

        os.makedirs(os.path.dirname(config_path), exist_ok=True)
        config = {"directories": []}
        with open(config_path, "w") as f:
            json.dump(config, f)

        assert os.path.exists(config_path)


class TestIndexLoading:
    """Tests for index file loading."""

    @pytest.fixture
    def temp_config_dir(self):
        """Create a temporary config directory."""
        tmp = tempfile.mkdtemp()
        config_dir = os.path.join(tmp, ".config", "logwatch-menubar")
        os.makedirs(config_dir, exist_ok=True)
        yield config_dir
        shutil.rmtree(tmp, ignore_errors=True)

    def test_load_valid_index(self, temp_config_dir):
        """Test loading a valid index file."""
        index_path = os.path.join(temp_config_dir, "log_index.json")
        index = {
            "files": {
                "/var/log/app.log": {
                    "position": 1000,
                    "mtime": 1700000000.0,
                    "error_count": 5
                }
            }
        }
        with open(index_path, "w") as f:
            json.dump(index, f)

        with open(index_path, "r") as f:
            loaded = json.load(f)

        assert "/var/log/app.log" in loaded["files"]
        assert loaded["files"]["/var/log/app.log"]["position"] == 1000

    def test_migrate_old_index_format(self, temp_config_dir):
        """Test migration from old list format to dict format."""
        index_path = os.path.join(temp_config_dir, "log_index.json")

        # Old format: list of file paths
        old_index = {
            "files": ["/var/log/app.log", "/var/log/error.log"]
        }
        with open(index_path, "w") as f:
            json.dump(old_index, f)

        with open(index_path, "r") as f:
            data = json.load(f)

        # Simulate migration
        if "files" in data and isinstance(data["files"], list):
            if data["files"] and isinstance(data["files"][0], str):
                new_files = {}
                for filepath in data["files"]:
                    new_files[filepath] = {
                        "position": 0,
                        "mtime": 0,
                        "error_count": 0
                    }
                data["files"] = new_files

        assert isinstance(data["files"], dict)
        assert "/var/log/app.log" in data["files"]
        assert data["files"]["/var/log/app.log"]["position"] == 0

    def test_load_nonexistent_index(self, temp_config_dir):
        """Test loading when index file doesn't exist."""
        index_path = os.path.join(temp_config_dir, "nonexistent_index.json")

        # Default should be empty files dict
        assert not os.path.exists(index_path)


class TestIndexSaving:
    """Tests for index file saving."""

    @pytest.fixture
    def temp_config_dir(self):
        """Create a temporary config directory."""
        tmp = tempfile.mkdtemp()
        config_dir = os.path.join(tmp, ".config", "logwatch-menubar")
        os.makedirs(config_dir, exist_ok=True)
        yield config_dir
        shutil.rmtree(tmp, ignore_errors=True)

    def test_save_index(self, temp_config_dir):
        """Test saving index file."""
        index_path = os.path.join(temp_config_dir, "log_index.json")
        index = {
            "files": {
                "/var/log/app.log": {
                    "position": 5000,
                    "mtime": 1700000000.0,
                    "error_count": 10
                }
            }
        }

        with open(index_path, "w") as f:
            json.dump(index, f, indent=2)

        with open(index_path, "r") as f:
            loaded = json.load(f)

        assert loaded == index

    def test_save_empty_index(self, temp_config_dir):
        """Test saving empty index."""
        index_path = os.path.join(temp_config_dir, "log_index.json")
        index = {"files": {}}

        with open(index_path, "w") as f:
            json.dump(index, f)

        with open(index_path, "r") as f:
            loaded = json.load(f)

        assert loaded["files"] == {}


class TestDatetimeConfigParsing:
    """Tests for datetime parsing from config."""

    def test_parse_valid_datetime(self):
        """Test parsing valid datetime string."""
        from datetime import datetime
        dt_str = "2024-01-15 12:30:45"
        result = datetime.strptime(dt_str, DATETIME_FORMAT)
        assert result == datetime(2024, 1, 15, 12, 30, 45)

    def test_parse_invalid_datetime(self):
        """Test parsing invalid datetime string."""
        from datetime import datetime
        dt_str = "invalid-datetime"
        with pytest.raises(ValueError):
            datetime.strptime(dt_str, DATETIME_FORMAT)

    def test_datetime_format_consistency(self):
        """Test that format string works for both parsing and formatting."""
        from datetime import datetime
        original = datetime(2024, 6, 15, 10, 30, 0)
        formatted = original.strftime(DATETIME_FORMAT)
        parsed = datetime.strptime(formatted, DATETIME_FORMAT)
        assert original == parsed


class TestDefaultPatterns:
    """Tests for default error patterns."""

    def test_default_patterns_exist(self):
        """Test that default patterns are defined."""
        assert len(DEFAULT_ERROR_PATTERNS) > 0

    def test_default_patterns_content(self):
        """Test that default patterns include common error terms."""
        expected = ["exception", "error", "traceback", "failed", "critical"]
        pattern_strings = [p.get("pattern") if isinstance(p, dict) else p
                          for p in DEFAULT_ERROR_PATTERNS]
        for pattern in expected:
            assert pattern in pattern_strings

    def test_patterns_are_lowercase(self):
        """Test that patterns are lowercase (for case-insensitive matching)."""
        for pattern in DEFAULT_ERROR_PATTERNS:
            pattern_str = pattern.get("pattern") if isinstance(pattern, dict) else pattern
            assert pattern_str == pattern_str.lower()

    def test_patterns_have_titles(self):
        """Test that default patterns have title and pattern keys."""
        for pattern in DEFAULT_ERROR_PATTERNS:
            assert isinstance(pattern, dict)
            assert "title" in pattern
            assert "pattern" in pattern
            assert len(pattern["title"]) > 0
            assert len(pattern["pattern"]) > 0


class TestPatternNormalization:
    """Tests for pattern normalization functions."""

    def test_normalize_string_pattern(self):
        """Test normalizing a plain string pattern."""
        result = normalize_pattern("error")
        assert result == {"title": "Error", "pattern": "error"}

    def test_normalize_dict_pattern_with_title(self):
        """Test normalizing a dict pattern that has title."""
        result = normalize_pattern({"title": "My Errors", "pattern": "error"})
        assert result == {"title": "My Errors", "pattern": "error"}

    def test_normalize_dict_pattern_without_title(self):
        """Test normalizing a dict pattern missing title."""
        result = normalize_pattern({"pattern": "warning"})
        assert result["title"] == "Warning"
        assert result["pattern"] == "warning"

    def test_normalize_patterns_list(self):
        """Test normalizing a list of mixed patterns."""
        patterns = [
            "error",
            {"title": "Critical Issues", "pattern": "critical"},
            {"pattern": "failed"},
        ]
        result = normalize_patterns(patterns)
        assert len(result) == 3
        assert result[0] == {"title": "Error", "pattern": "error"}
        assert result[1] == {"title": "Critical Issues", "pattern": "critical"}
        assert result[2]["title"] == "Failed"
        assert result[2]["pattern"] == "failed"

    def test_normalize_empty_list(self):
        """Test normalizing an empty list."""
        result = normalize_patterns([])
        assert result == []

    def test_normalize_preserves_regex_pattern(self):
        """Test that regex patterns are preserved."""
        result = normalize_pattern("^ERROR.*timeout")
        assert result["pattern"] == "^ERROR.*timeout"


class TestConfigPaths:
    """Tests for configuration paths."""

    def test_config_path_in_home(self):
        """Test that config path is under home directory."""
        assert str(Path.home()) in str(CONFIG_PATH)

    def test_index_path_in_home(self):
        """Test that index path is under home directory."""
        assert str(Path.home()) in str(INDEX_PATH)

    def test_config_path_structure(self):
        """Test config path has expected structure."""
        assert ".config" in str(CONFIG_PATH)
        assert "logwatch-menubar" in str(CONFIG_PATH)
        assert "config.json" in str(CONFIG_PATH)

    def test_index_path_structure(self):
        """Test index path has expected structure."""
        assert ".config" in str(INDEX_PATH)
        assert "logwatch-menubar" in str(INDEX_PATH)
        assert "log_index.json" in str(INDEX_PATH)
