"""
Pytest configuration and fixtures for logwatch-menubar tests.
"""

import os
import sys
import json
import tempfile
import shutil
from pathlib import Path
from datetime import datetime

import pytest

# Add parent directory to path so we can import the main module
sys.path.insert(0, str(Path(__file__).parent.parent))


@pytest.fixture
def temp_dir():
    """Create a temporary directory for test files."""
    tmp = tempfile.mkdtemp()
    yield tmp
    shutil.rmtree(tmp, ignore_errors=True)


@pytest.fixture
def temp_log_file(temp_dir):
    """Create a temporary log file with sample content."""
    log_path = os.path.join(temp_dir, "test.log")
    with open(log_path, "w") as f:
        f.write("2024-01-15 10:00:00 INFO Starting application\n")
        f.write("2024-01-15 10:00:01 DEBUG Loading configuration\n")
        f.write("2024-01-15 10:00:02 ERROR Failed to connect to database\n")
        f.write("2024-01-15 10:00:03 INFO Retrying connection\n")
        f.write("2024-01-15 10:00:04 CRITICAL System shutdown\n")
    return log_path


@pytest.fixture
def temp_config_dir(temp_dir):
    """Create a temporary config directory."""
    config_dir = os.path.join(temp_dir, ".config", "logwatch-menubar")
    os.makedirs(config_dir, exist_ok=True)
    return config_dir


@pytest.fixture
def sample_config(temp_config_dir):
    """Create a sample configuration file."""
    config_path = os.path.join(temp_config_dir, "config.json")
    config = {
        "directories": ["/tmp/logs"],
        "sound_enabled": True,
        "error_patterns": ["error", "exception", "critical"],
        "start_datetime": "2024-01-01 00:00:00",
        "end_datetime": "2024-12-31 23:59:59"
    }
    with open(config_path, "w") as f:
        json.dump(config, f)
    return config_path


@pytest.fixture
def sample_index(temp_config_dir):
    """Create a sample index file."""
    index_path = os.path.join(temp_config_dir, "log_index.json")
    index = {
        "files": {
            "/tmp/logs/app.log": {
                "position": 1000,
                "mtime": 1700000000.0,
                "error_count": 5
            }
        }
    }
    with open(index_path, "w") as f:
        json.dump(index, f)
    return index_path


@pytest.fixture
def mock_callback():
    """Create a mock callback that records calls."""
    calls = []
    def callback(*args, **kwargs):
        calls.append((args, kwargs))
    callback.calls = calls
    return callback


@pytest.fixture
def log_directory_structure(temp_dir):
    """Create a directory structure with various log files for testing."""
    # Create subdirectories
    subdir1 = os.path.join(temp_dir, "app")
    subdir2 = os.path.join(temp_dir, "system")
    hidden_dir = os.path.join(temp_dir, ".hidden")
    node_modules = os.path.join(temp_dir, "node_modules")

    for d in [subdir1, subdir2, hidden_dir, node_modules]:
        os.makedirs(d, exist_ok=True)

    # Create log files
    log_files = [
        (os.path.join(temp_dir, "main.log"), True),
        (os.path.join(subdir1, "app.log"), True),
        (os.path.join(subdir1, "debug.log"), True),
        (os.path.join(subdir2, "system.log"), True),
        (os.path.join(hidden_dir, "hidden.log"), False),  # Should be skipped
        (os.path.join(node_modules, "package.log"), False),  # Should be skipped
        (os.path.join(temp_dir, "readme.txt"), False),  # Not a log file
    ]

    for filepath, is_log in log_files:
        with open(filepath, "w") as f:
            if is_log:
                f.write("2024-01-15 10:00:00 INFO Log entry\n")
                f.write("2024-01-15 10:00:01 INFO Another entry\n")
            else:
                f.write("Not a log file\n")

    return temp_dir, [fp for fp, is_log in log_files if is_log]
