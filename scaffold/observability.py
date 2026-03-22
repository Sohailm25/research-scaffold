# ABOUTME: Structured JSONL logging for experiment sessions.
# ABOUTME: Writes timestamped events to per-session log files for observability and debugging.

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path


@dataclass
class Event:
    """A single observability event."""

    event_type: str
    session_id: str
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    data: dict = field(default_factory=dict)


class SessionLogger:
    """Writes structured JSONL events to a session log file."""

    def __init__(self, log_dir: Path, session_id: str):
        """Create logger. Creates log_dir if needed."""
        self.log_dir = log_dir
        self.session_id = session_id
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.log_path = self.log_dir / f"{session_id}.jsonl"

    def log(self, event_type: str, **data) -> Event:
        """Log an event. Writes JSON line to log file. Returns the Event."""
        event = Event(event_type=event_type, session_id=self.session_id, data=data)
        with open(self.log_path, "a") as f:
            f.write(json.dumps(asdict(event)) + "\n")
        return event

    def read_events(self) -> list[Event]:
        """Read all events from the log file. Returns empty list if file missing."""
        events = []
        if self.log_path.exists():
            with open(self.log_path) as f:
                for line in f:
                    line = line.strip()
                    if line:
                        d = json.loads(line)
                        events.append(Event(**d))
        return events
