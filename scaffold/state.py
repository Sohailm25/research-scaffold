# ABOUTME: Experiment state machine with phase transitions and JSON persistence.
# ABOUTME: Tracks phase statuses, enforces valid transitions, and serializes to/from JSON.

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

# Valid phase status transitions: {current_status: set(allowed_next_statuses)}
VALID_TRANSITIONS: dict[str, set[str]] = {
    "NOT_STARTED": {"IN_PROGRESS"},
    "IN_PROGRESS": {"GATE_CHECK"},
    "GATE_CHECK": {"GATE_PASSED", "GATE_FAILED", "NEGATIVE_RESULT"},
    "GATE_PASSED": {"HUMAN_REVIEW", "COMPLETED"},
    "GATE_FAILED": {"IN_PROGRESS"},
    "HUMAN_REVIEW": {"COMPLETED"},
    "NEGATIVE_RESULT": {"COMPLETED"},
    "COMPLETED": set(),
}

PHASE_STATUSES = frozenset(VALID_TRANSITIONS.keys())

EXPERIMENT_STATUSES = frozenset({
    "PLANNING",
    "ACTIVE",
    "PAUSED",
    "WRITING",
    "COMPLETED",
    "NEGATIVE_RESULT",
})


def _now_iso() -> str:
    """Return current UTC time as ISO 8601 string."""
    return datetime.now(timezone.utc).isoformat()


@dataclass
class PhaseState:
    """State of a single experiment phase."""

    name: str
    status: str = "NOT_STARTED"
    iteration_count: int = 0
    metrics: dict = field(default_factory=dict)
    metrics_history: list[dict] = field(default_factory=list)


@dataclass
class ExperimentState:
    """State of an entire experiment with phase tracking and persistence."""

    experiment_name: str
    status: str = "PLANNING"
    phases: list[PhaseState] = field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""
    current_phase: str | None = None

    def __post_init__(self) -> None:
        """Set timestamps to the same value if not explicitly provided."""
        if not self.created_at:
            now = _now_iso()
            self.created_at = now
            self.updated_at = now
        elif not self.updated_at:
            self.updated_at = self.created_at

    @classmethod
    def from_config(cls, config) -> ExperimentState:
        """Create initial ExperimentState from an experiment config object.

        The config must have `name` (str) and `phases` (list of PhaseConfig objects).
        """
        phases = [PhaseState(name=p.name) for p in config.phases]
        return cls(experiment_name=config.name, phases=phases)

    def advance_phase(self, phase_name: str, new_status: str) -> None:
        """Advance a phase to a new status, validating the transition.

        Raises ValueError if the phase is not found or the transition is invalid.
        """
        phase = self._find_phase(phase_name)

        allowed = VALID_TRANSITIONS.get(phase.status, set())
        if new_status not in allowed:
            raise ValueError(
                f"Invalid transition: {phase.status} -> {new_status} "
                f"for phase '{phase_name}'. "
                f"Allowed transitions: {sorted(allowed) if allowed else 'none (terminal state)'}"
            )

        # Increment iteration count when retrying after gate failure
        if phase.status == "GATE_FAILED" and new_status == "IN_PROGRESS":
            phase.iteration_count += 1

        phase.status = new_status
        self.updated_at = _now_iso()

    def get_current_phase(self) -> PhaseState | None:
        """Return the first non-COMPLETED phase, or None if all phases are done."""
        for phase in self.phases:
            if phase.status != "COMPLETED":
                return phase
        return None

    def save(self, path: Path) -> None:
        """Save experiment state to a JSON file, creating parent dirs if needed."""
        path.parent.mkdir(parents=True, exist_ok=True)
        data = asdict(self)
        path.write_text(json.dumps(data, indent=2) + "\n")

    @classmethod
    def load(cls, path: Path) -> ExperimentState:
        """Load experiment state from a JSON file."""
        data = json.loads(path.read_text())
        phases = []
        for p in data.pop("phases"):
            if "metrics_history" not in p:
                p["metrics_history"] = []
            phases.append(PhaseState(**p))
        return cls(phases=phases, **data)

    def _find_phase(self, phase_name: str) -> PhaseState:
        """Find a phase by name or raise ValueError."""
        for phase in self.phases:
            if phase.name == phase_name:
                return phase
        raise ValueError(f"Phase '{phase_name}' not found in experiment '{self.experiment_name}'")
