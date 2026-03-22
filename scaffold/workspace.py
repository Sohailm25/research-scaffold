# ABOUTME: Manages experiment workspace directories with safety invariants.
# ABOUTME: Provides path traversal prevention, workspace validation, and result/artifact path helpers.

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass
class WorkspaceManager:
    """Manages an experiment workspace directory with safety checks."""

    root: Path
    experiment_name: str

    @property
    def experiment_dir(self) -> Path:
        """Root directory for this experiment."""
        return self.root / self.experiment_name

    def validate(self) -> None:
        """Validate workspace exists and has expected structure.

        Raises FileNotFoundError if experiment_dir doesn't exist.
        Raises ValueError if critical files missing (AGENTS.md, configs/experiment.yaml).
        """
        if not self.experiment_dir.exists():
            raise FileNotFoundError(
                f"Experiment directory does not exist: {self.experiment_dir}"
            )

        agents_path = self.experiment_dir / "AGENTS.md"
        if not agents_path.exists():
            raise ValueError(f"Missing critical file: AGENTS.md in {self.experiment_dir}")

        config_path = self.experiment_dir / "configs" / "experiment.yaml"
        if not config_path.exists():
            raise ValueError(
                f"Missing critical file: configs/experiment.yaml in {self.experiment_dir}"
            )

    def safe_path(self, relative: str) -> Path:
        """Resolve a relative path within the workspace, preventing path traversal.

        Raises ValueError if the resolved path would escape the experiment directory.
        Returns the resolved absolute path.
        """
        resolved = (self.experiment_dir / relative).resolve()
        experiment_resolved = self.experiment_dir.resolve()

        if not str(resolved).startswith(str(experiment_resolved) + "/") and resolved != experiment_resolved:
            raise ValueError(
                f"Path would escape experiment directory: '{relative}'"
            )
        return resolved

    def result_dir(self, lane: str) -> Path:
        """Get the results directory for a specific lane. Creates it if needed.

        Validates lane name (no path separators, no dots).
        """
        if "/" in lane or "\\" in lane or ".." in lane:
            raise ValueError(
                f"Invalid lane name '{lane}': must not contain path separators or '..'"
            )
        path = self.experiment_dir / "results" / lane
        path.mkdir(parents=True, exist_ok=True)
        return path

    def artifact_path(self, lane: str, filename: str) -> Path:
        """Get a safe path for an artifact file within a lane's results directory."""
        if ".." in filename or "/" in filename or "\\" in filename:
            raise ValueError(
                f"Invalid artifact filename '{filename}': must not contain path traversal"
            )
        lane_dir = self.result_dir(lane)
        return lane_dir / filename

    def session_dir(self) -> Path:
        """Get the sessions directory path."""
        return self.experiment_dir / "sessions"
