# ABOUTME: Tests for the structured JSONL session logging module.
# ABOUTME: Verifies event creation, file I/O, roundtrip serialization, and edge cases.

from __future__ import annotations

import json

from scaffold.observability import Event, SessionLogger


class TestEvent:
    """Tests for Event dataclass defaults and field presence."""

    def test_event_has_required_fields(self):
        """Event stores event_type, session_id, timestamp, and data."""
        event = Event(event_type="phase_started", session_id="sess-001")
        assert event.event_type == "phase_started"
        assert event.session_id == "sess-001"
        assert isinstance(event.timestamp, str)
        assert len(event.timestamp) > 0
        assert isinstance(event.data, dict)

    def test_event_default_data_is_empty_dict(self):
        """Data defaults to empty dict when not provided."""
        event = Event(event_type="test", session_id="s1")
        assert event.data == {}


class TestSessionLogger:
    """Tests for SessionLogger JSONL file operations."""

    def test_creates_log_directory(self, tmp_path):
        """Logger creates log_dir if it does not exist."""
        log_dir = tmp_path / "logs" / "nested"
        assert not log_dir.exists()
        SessionLogger(log_dir=log_dir, session_id="sess-001")
        assert log_dir.exists()

    def test_log_creates_jsonl_file(self, tmp_path):
        """First log call creates the .jsonl file."""
        logger = SessionLogger(log_dir=tmp_path, session_id="sess-001")
        assert not logger.log_path.exists()
        logger.log("test_event")
        assert logger.log_path.exists()
        assert logger.log_path.name == "sess-001.jsonl"

    def test_log_writes_valid_json_lines(self, tmp_path):
        """Each log call appends exactly one valid JSON line."""
        logger = SessionLogger(log_dir=tmp_path, session_id="sess-002")
        logger.log("event_a")
        logger.log("event_b")

        lines = logger.log_path.read_text().strip().split("\n")
        assert len(lines) == 2
        for line in lines:
            parsed = json.loads(line)
            assert "event_type" in parsed

    def test_log_event_has_required_fields(self, tmp_path):
        """Logged JSON contains event_type, session_id, and timestamp."""
        logger = SessionLogger(log_dir=tmp_path, session_id="sess-003")
        logger.log("phase_started")

        line = logger.log_path.read_text().strip()
        parsed = json.loads(line)
        assert parsed["event_type"] == "phase_started"
        assert parsed["session_id"] == "sess-003"
        assert "timestamp" in parsed
        assert len(parsed["timestamp"]) > 0

    def test_log_includes_data_payload(self, tmp_path):
        """Keyword arguments to log() appear in the data field."""
        logger = SessionLogger(log_dir=tmp_path, session_id="sess-004")
        logger.log("gate_evaluated", metric="accuracy", value=0.95)

        line = logger.log_path.read_text().strip()
        parsed = json.loads(line)
        assert parsed["data"]["metric"] == "accuracy"
        assert parsed["data"]["value"] == 0.95

    def test_multiple_logs_append(self, tmp_path):
        """Multiple log calls append to the same file, not overwrite."""
        logger = SessionLogger(log_dir=tmp_path, session_id="sess-005")
        logger.log("first")
        logger.log("second")
        logger.log("third")

        lines = logger.log_path.read_text().strip().split("\n")
        assert len(lines) == 3
        types = [json.loads(line)["event_type"] for line in lines]
        assert types == ["first", "second", "third"]

    def test_read_events_roundtrip(self, tmp_path):
        """Events written by log() can be read back by read_events()."""
        logger = SessionLogger(log_dir=tmp_path, session_id="sess-006")
        logger.log("alpha", key="val1")
        logger.log("beta", key="val2")

        events = logger.read_events()
        assert len(events) == 2
        assert events[0].event_type == "alpha"
        assert events[0].data["key"] == "val1"
        assert events[1].event_type == "beta"
        assert events[1].session_id == "sess-006"

    def test_read_events_empty_file(self, tmp_path):
        """read_events() returns empty list when log file does not exist."""
        logger = SessionLogger(log_dir=tmp_path, session_id="sess-007")
        events = logger.read_events()
        assert events == []

    def test_log_returns_event(self, tmp_path):
        """log() returns the Event object that was written."""
        logger = SessionLogger(log_dir=tmp_path, session_id="sess-008")
        event = logger.log("run_completed", duration=12.5)
        assert isinstance(event, Event)
        assert event.event_type == "run_completed"
        assert event.data["duration"] == 12.5
        assert event.session_id == "sess-008"
