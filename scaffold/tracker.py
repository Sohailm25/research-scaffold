# ABOUTME: Adapter for beads (bd) CLI issue tracking within experiments.
# ABOUTME: Wraps bd commands for lane issues, phase milestones, and sync.

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass
class BeadsResult:
    """Result from a beads CLI command."""

    success: bool
    stdout: str
    stderr: str
    returncode: int


class BeadsTracker:
    """Adapter for beads (bd) CLI commands."""

    def __init__(self, experiment_dir: Path):
        self.experiment_dir = experiment_dir

    def _run(self, args: list[str]) -> BeadsResult:
        """Run a bd command in the experiment directory."""
        try:
            result = subprocess.run(
                ["bd"] + args,
                cwd=self.experiment_dir,
                capture_output=True,
                text=True,
                timeout=30,
            )
            return BeadsResult(
                success=result.returncode == 0,
                stdout=result.stdout,
                stderr=result.stderr,
                returncode=result.returncode,
            )
        except FileNotFoundError:
            return BeadsResult(
                success=False,
                stdout="",
                stderr="bd command not found",
                returncode=-1,
            )
        except subprocess.TimeoutExpired:
            return BeadsResult(
                success=False,
                stdout="",
                stderr="bd command timed out",
                returncode=-1,
            )

    def init(self) -> BeadsResult:
        """Initialize beads in the experiment directory."""
        return self._run(["init"])

    def create_issue(self, title: str, issue_type: str = "task", priority: int = 2) -> BeadsResult:
        """Create a new beads issue."""
        return self._run(["create", title, "--type", issue_type, "--priority", str(priority)])

    def create_lane_issues(self, lanes: list[str]) -> list[BeadsResult]:
        """Create one issue per required lane."""
        results = []
        for lane in lanes:
            results.append(self.create_issue(f"{lane} lane"))
        return results

    def create_phase_milestones(self, phases: list[str]) -> list[BeadsResult]:
        """Create milestone issues for each phase."""
        results = []
        for phase in phases:
            results.append(self.create_issue(phase, issue_type="milestone", priority=1))
        return results

    def close(self, issue_id: str) -> BeadsResult:
        """Close a beads issue."""
        return self._run(["close", issue_id])

    def sync(self) -> BeadsResult:
        """Sync beads with git."""
        return self._run(["sync"])

    def ready(self) -> BeadsResult:
        """Find unblocked work."""
        return self._run(["ready"])
