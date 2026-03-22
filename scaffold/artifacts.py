# ABOUTME: Artifact registry with dual persistence (JSON + Markdown).
# ABOUTME: Tracks experimental artifacts by lane with machine-readable and human-readable outputs.

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

VALID_STATUSES = frozenset({"pass", "fail", "mixed", "partial", "planning", "superseded"})

MARKDOWN_HEADER = """# Results Index

Register every experimental artifact here. Never delete entries; mark superseded artifacts explicitly.

## Rules

- Every artifact saved under `results/` must appear here.
- Every entry should state the relevant hypothesis or lane.
- Every entry should state `pass`, `fail`, `mixed`, `partial`, or `planning`.
- Every summary must respect the framing locks in `history/PREREG.md`.
"""


def _now_iso() -> str:
    """Return current UTC time as ISO 8601 string."""
    return datetime.now(timezone.utc).isoformat()


def _lane_to_heading(lane: str) -> str:
    """Convert a lane name like 'oracle_alpha' to a section heading like 'Oracle Alpha'."""
    return lane.replace("_", " ").title()


@dataclass
class Artifact:
    """A single experimental artifact with metadata."""

    name: str
    lane: str
    status: str
    path: str
    description: str = ""
    registered_at: str = field(default_factory=_now_iso)


class ArtifactRegistry:
    """Registry of experimental artifacts with dual JSON/Markdown persistence."""

    def __init__(self, root: Path) -> None:
        self._root = root
        self._artifacts: list[Artifact] = []

    def register(self, artifact: Artifact) -> None:
        """Add an artifact to the registry."""
        self._artifacts.append(artifact)

    def update_status(self, name: str, new_status: str) -> None:
        """Update the status of an artifact by name.

        Raises ValueError if the artifact is not found.
        """
        artifact = self._find(name)
        artifact.status = new_status

    def supersede(self, name: str) -> None:
        """Mark an artifact as superseded.

        Raises ValueError if the artifact is not found.
        """
        self.update_status(name, "superseded")

    def get_by_lane(self, lane: str) -> list[Artifact]:
        """Return all artifacts belonging to the given lane."""
        return [a for a in self._artifacts if a.lane == lane]

    def save(self) -> None:
        """Write both .scaffold/artifacts.json and results/RESULTS_INDEX.md."""
        # JSON persistence
        json_dir = self._root / ".scaffold"
        json_dir.mkdir(parents=True, exist_ok=True)
        json_path = json_dir / "artifacts.json"
        data = [asdict(a) for a in self._artifacts]
        json_path.write_text(json.dumps(data, indent=2) + "\n")

        # Markdown persistence
        results_dir = self._root / "results"
        results_dir.mkdir(parents=True, exist_ok=True)
        md_path = results_dir / "RESULTS_INDEX.md"
        md_path.write_text(self.render_markdown())

    @classmethod
    def load(cls, root: Path) -> ArtifactRegistry:
        """Load artifact registry from .scaffold/artifacts.json."""
        json_path = root / ".scaffold" / "artifacts.json"
        data = json.loads(json_path.read_text())
        registry = cls(root)
        for item in data:
            registry.register(Artifact(**item))
        return registry

    def render_markdown(self) -> str:
        """Render the RESULTS_INDEX.md content grouped by lane."""
        lines = [MARKDOWN_HEADER.rstrip()]

        # Group artifacts by lane, preserving insertion order
        lanes: dict[str, list[Artifact]] = {}
        for artifact in self._artifacts:
            lanes.setdefault(artifact.lane, []).append(artifact)

        for lane, artifacts in lanes.items():
            heading = _lane_to_heading(lane)
            lines.append(f"\n## {heading}\n")
            lines.append("| Artifact | Lane | Status | Path |")
            lines.append("|---|---|---|---|")
            for a in artifacts:
                lines.append(f"| {a.name} | {a.lane} | {a.status} | {a.path} |")

        return "\n".join(lines) + "\n"

    def _find(self, name: str) -> Artifact:
        """Find an artifact by name or raise ValueError."""
        for artifact in self._artifacts:
            if artifact.name == name:
                return artifact
        raise ValueError(f"Artifact '{name}' not found in registry")
