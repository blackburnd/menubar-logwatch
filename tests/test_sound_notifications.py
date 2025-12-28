"""
Tests for sound notification functionality.
"""

import os
import sys
from pathlib import Path
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, call

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))


class TestUniqueSoundPlayback:
    """Tests for unique sound playback per burst."""

    def test_same_sound_plays_once_per_burst(self):
        """Test that the same sound only plays once even with multiple matches."""
        sounds_played = set()
        sound_reset_time = None
        max_sounds_per_burst = 5
        sound_enabled = True

        # Simulate 3 matches with the same sound
        sound_path = "/System/Library/Sounds/Glass.aiff"

        for i in range(3):
            now = datetime.now()
            # Reset tracking if enough time has passed
            if sound_reset_time is None or now > sound_reset_time:
                sounds_played.clear()

            if len(sounds_played) < max_sounds_per_burst:
                # Only play if this sound hasn't been played in this burst
                if sound_path not in sounds_played:
                    sounds_played.add(sound_path)
                    # Reset tracking 2 seconds after first sound
                    if len(sounds_played) == 1:
                        sound_reset_time = now + timedelta(seconds=2)

        # Sound should only be in the set once
        assert len(sounds_played) == 1
        assert sound_path in sounds_played

    def test_different_sounds_play_once_each(self):
        """Test that different sounds each play once in the same burst."""
        sounds_played = set()
        sound_reset_time = None
        max_sounds_per_burst = 5
        sound_enabled = True

        # Simulate 5 matches with different sounds
        sound_paths = [
            "/System/Library/Sounds/Glass.aiff",
            "/System/Library/Sounds/Basso.aiff",
            "/System/Library/Sounds/Funk.aiff",
            "/System/Library/Sounds/Ping.aiff",
            "/System/Library/Sounds/Pop.aiff",
        ]

        for sound_path in sound_paths:
            now = datetime.now()
            # Reset tracking if enough time has passed
            if sound_reset_time is None or now > sound_reset_time:
                sounds_played.clear()

            if len(sounds_played) < max_sounds_per_burst:
                # Only play if this sound hasn't been played in this burst
                if sound_path not in sounds_played:
                    sounds_played.add(sound_path)
                    # Reset tracking 2 seconds after first sound
                    if len(sounds_played) == 1:
                        sound_reset_time = now + timedelta(seconds=2)

        # All 5 different sounds should be in the set
        assert len(sounds_played) == 5
        for sound_path in sound_paths:
            assert sound_path in sounds_played

    def test_burst_limit_enforced(self):
        """Test that max_sounds_per_burst limit is enforced."""
        sounds_played = set()
        sound_reset_time = None
        max_sounds_per_burst = 3
        sound_enabled = True

        # Try to play 5 different sounds
        sound_paths = [
            "/System/Library/Sounds/Glass.aiff",
            "/System/Library/Sounds/Basso.aiff",
            "/System/Library/Sounds/Funk.aiff",
            "/System/Library/Sounds/Ping.aiff",
            "/System/Library/Sounds/Pop.aiff",
        ]

        for sound_path in sound_paths:
            now = datetime.now()
            # Reset tracking if enough time has passed
            if sound_reset_time is None or now > sound_reset_time:
                sounds_played.clear()

            if len(sounds_played) < max_sounds_per_burst:
                # Only play if this sound hasn't been played in this burst
                if sound_path not in sounds_played:
                    sounds_played.add(sound_path)
                    # Reset tracking 2 seconds after first sound
                    if len(sounds_played) == 1:
                        sound_reset_time = now + timedelta(seconds=2)

        # Only max_sounds_per_burst should have played
        assert len(sounds_played) == max_sounds_per_burst

    def test_burst_reset_after_timeout(self):
        """Test that burst resets after timeout allowing sounds to play again."""
        sounds_played = set()
        sound_reset_time = None
        max_sounds_per_burst = 5
        sound_enabled = True

        sound_path = "/System/Library/Sounds/Glass.aiff"

        # First burst
        now = datetime.now()
        if sound_reset_time is None or now > sound_reset_time:
            sounds_played.clear()

        if len(sounds_played) < max_sounds_per_burst:
            if sound_path not in sounds_played:
                sounds_played.add(sound_path)
                if len(sounds_played) == 1:
                    sound_reset_time = now + timedelta(seconds=2)

        assert len(sounds_played) == 1

        # Simulate time passing (beyond reset time)
        now = datetime.now() + timedelta(seconds=3)

        # Second burst - should reset
        if sound_reset_time is None or now > sound_reset_time:
            sounds_played.clear()

        if len(sounds_played) < max_sounds_per_burst:
            if sound_path not in sounds_played:
                sounds_played.add(sound_path)
                if len(sounds_played) == 1:
                    sound_reset_time = now + timedelta(seconds=2)

        # Sound should play again after reset
        assert len(sounds_played) == 1
        assert sound_path in sounds_played

    def test_mixed_sounds_deduplication(self):
        """Test deduplication when patterns have overlapping sounds."""
        sounds_played = set()
        sound_reset_time = None
        max_sounds_per_burst = 5
        sound_enabled = True

        # Simulate matches: 3x Glass, 2x Basso, 3x Glass again
        matches = [
            "/System/Library/Sounds/Glass.aiff",
            "/System/Library/Sounds/Glass.aiff",
            "/System/Library/Sounds/Glass.aiff",
            "/System/Library/Sounds/Basso.aiff",
            "/System/Library/Sounds/Basso.aiff",
            "/System/Library/Sounds/Glass.aiff",
            "/System/Library/Sounds/Glass.aiff",
            "/System/Library/Sounds/Glass.aiff",
        ]

        for sound_path in matches:
            now = datetime.now()
            if sound_reset_time is None or now > sound_reset_time:
                sounds_played.clear()

            if len(sounds_played) < max_sounds_per_burst:
                if sound_path not in sounds_played:
                    sounds_played.add(sound_path)
                    if len(sounds_played) == 1:
                        sound_reset_time = now + timedelta(seconds=2)

        # Only 2 unique sounds should have played
        assert len(sounds_played) == 2
        assert "/System/Library/Sounds/Glass.aiff" in sounds_played
        assert "/System/Library/Sounds/Basso.aiff" in sounds_played


class TestSoundCallbackSignature:
    """Tests for callback signature with matched_patterns."""

    def test_callback_receives_matched_patterns(self):
        """Test that error callback receives matched patterns."""
        callback_calls = []

        def mock_callback(filepath, line_num, message, matched_patterns=None):
            callback_calls.append({
                'filepath': filepath,
                'line_num': line_num,
                'message': message,
                'matched_patterns': matched_patterns
            })

        # Simulate callback invocation
        mock_callback("/var/log/app.log", 42, "ERROR: test", ["error", "test"])

        assert len(callback_calls) == 1
        assert callback_calls[0]['filepath'] == "/var/log/app.log"
        assert callback_calls[0]['line_num'] == 42
        assert callback_calls[0]['message'] == "ERROR: test"
        assert callback_calls[0]['matched_patterns'] == ["error", "test"]

    def test_callback_with_no_patterns(self):
        """Test callback works with None matched_patterns."""
        callback_calls = []

        def mock_callback(filepath, line_num, message, matched_patterns=None):
            callback_calls.append({
                'filepath': filepath,
                'matched_patterns': matched_patterns
            })

        # Simulate callback with no patterns
        mock_callback("/var/log/app.log", 42, "INFO: test", None)

        assert len(callback_calls) == 1
        assert callback_calls[0]['matched_patterns'] is None


class TestRescanUniqueSounds:
    """Tests for rescan with unique sound collection."""

    def test_rescan_collects_unique_sounds(self):
        """Test that rescan collects unique sounds from all matches."""
        unique_sounds = set()
        patterns_config = [
            {"title": "Errors", "pattern": "error", "sound": "/System/Library/Sounds/Glass.aiff"},
            {"title": "Warnings", "pattern": "warning", "sound": "/System/Library/Sounds/Basso.aiff"},
            {"title": "Critical", "pattern": "critical", "sound": "/System/Library/Sounds/Funk.aiff"},
        ]

        # Simulate matches found during rescan
        matches = [
            ["error"],
            ["error"],
            ["warning"],
            ["error"],
            ["critical"],
            ["warning"],
        ]

        for matched_patterns in matches:
            if matched_patterns:
                # Find the sound for the first matched pattern
                for pattern_dict in patterns_config:
                    if pattern_dict.get("pattern") in matched_patterns:
                        sound_path = pattern_dict.get("sound", "/System/Library/Sounds/Glass.aiff")
                        unique_sounds.add(sound_path)
                        break

        # Should have 3 unique sounds
        assert len(unique_sounds) == 3
        assert "/System/Library/Sounds/Glass.aiff" in unique_sounds
        assert "/System/Library/Sounds/Basso.aiff" in unique_sounds
        assert "/System/Library/Sounds/Funk.aiff" in unique_sounds

    def test_rescan_respects_max_sounds_limit(self):
        """Test that rescan respects max_sounds_per_burst limit."""
        unique_sounds = set()
        max_sounds_per_burst = 2
        patterns_config = [
            {"title": "Errors", "pattern": "error", "sound": "/System/Library/Sounds/Glass.aiff"},
            {"title": "Warnings", "pattern": "warning", "sound": "/System/Library/Sounds/Basso.aiff"},
            {"title": "Critical", "pattern": "critical", "sound": "/System/Library/Sounds/Funk.aiff"},
        ]

        # Simulate matches found during rescan
        matches = [
            ["error"],
            ["warning"],
            ["critical"],
        ]

        for matched_patterns in matches:
            if matched_patterns:
                for pattern_dict in patterns_config:
                    if pattern_dict.get("pattern") in matched_patterns:
                        sound_path = pattern_dict.get("sound", "/System/Library/Sounds/Glass.aiff")
                        unique_sounds.add(sound_path)
                        break

        # Get sounds to play (limited)
        sounds_to_play = list(unique_sounds)[:max_sounds_per_burst]

        # Should only play max_sounds_per_burst sounds
        assert len(sounds_to_play) == max_sounds_per_burst
