# ABOUTME: Main execution loop that drives experiment phases through dispatch, gates, and state transitions.
# ABOUTME: Coordinates runner, gate evaluation, state persistence, and observability logging.

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from scaffold.artifacts import ArtifactRegistry
from scaffold.config import ExperimentConfig, load_config
from scaffold.gates import PhaseGateReport, evaluate_phase_gates
from scaffold.observability import SessionLogger
from scaffold.runner import AgentRunner, RunResult
from scaffold.state import ExperimentState
from scaffold.workflow import load_workflow, render_prompt
from scaffold.workspace import WorkspaceManager


@dataclass
class PhaseResult:
    """Result of executing a single phase."""

    phase_name: str
    gate_passed: bool
    negative_result: bool = False
    iterations: int = 0
    requires_human_review: bool = False
    gate_report: dict | None = None


class Orchestrator:
    """Drives experiment phases: dispatch work, evaluate gates, advance state."""

    def __init__(
        self,
        experiment_dir: Path,
        runner: AgentRunner,
        max_iterations: int = 20,
    ):
        self.experiment_dir = experiment_dir
        self.runner = runner
        self.max_iterations = max_iterations

        # Load config and state
        self.config = load_config(experiment_dir / "configs" / "experiment.yaml")
        self.state = ExperimentState.load(
            experiment_dir / ".scaffold" / "state.json"
        )
        self.artifacts = ArtifactRegistry.load(experiment_dir)
        self.workspace = WorkspaceManager(
            root=experiment_dir.parent, experiment_name=experiment_dir.name
        )
        self.logger = SessionLogger(
            log_dir=experiment_dir / "sessions" / "logs",
            session_id=f"orchestrator-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}",
        )

    def run_phase(self, phase_name: str) -> PhaseResult:
        """Execute a single phase with iterative gate-check loop.

        State transitions per iteration:
          NOT_STARTED -> IN_PROGRESS -> GATE_CHECK -> GATE_PASSED/GATE_FAILED
          GATE_FAILED -> IN_PROGRESS (retry, increments iteration_count)
          GATE_PASSED -> COMPLETED or HUMAN_REVIEW

        Returns PhaseResult summarizing the outcome.
        """
        # Find the phase config
        phase_config = None
        for p in self.config.phases:
            if p.name == phase_name:
                phase_config = p
                break
        if phase_config is None:
            raise ValueError(f"Phase '{phase_name}' not found in config")

        self.logger.log("phase_started", phase=phase_name)

        # Load workflow for prompt rendering
        workflow_path = self.experiment_dir / "WORKFLOW.md"
        workflow = load_workflow(workflow_path) if workflow_path.exists() else None

        iterations = 0

        while iterations < self.max_iterations:
            iterations += 1

            # Advance to IN_PROGRESS
            phase_state = self.state._find_phase(phase_name)
            if phase_state.status == "NOT_STARTED":
                self.state.advance_phase(phase_name, "IN_PROGRESS")
            elif phase_state.status == "GATE_FAILED":
                self.state.advance_phase(phase_name, "IN_PROGRESS")
            # If already IN_PROGRESS (e.g. first iteration after retry), proceed

            self._save_state()

            # Build prompt
            prompt = phase_name
            if workflow is not None:
                context = {
                    "phase": phase_name,
                    "lane": phase_config.name,
                    "task": phase_config.description,
                }
                try:
                    prompt = render_prompt(workflow, context)
                except Exception:
                    prompt = phase_name

            # Dispatch to runner
            try:
                run_result = self.runner.execute(
                    prompt, cwd=self.experiment_dir
                )
            except Exception as exc:
                self.logger.log(
                    "run_error", phase=phase_name, error=str(exc)
                )
                run_result = RunResult(
                    success=False, stderr=str(exc), returncode=-1
                )

            # Advance to GATE_CHECK
            self.state.advance_phase(phase_name, "GATE_CHECK")
            self._save_state()

            # Collect metrics and evaluate gates
            metrics = self._collect_metrics(phase_name)
            report = evaluate_phase_gates(phase_config, metrics)

            self.logger.log(
                "gate_evaluated",
                phase=phase_name,
                overall_pass=report.overall_pass,
                iteration=iterations,
            )

            if report.overall_pass:
                # Gates passed
                self.state.advance_phase(phase_name, "GATE_PASSED")
                self._save_state()

                if phase_config.requires_human_review:
                    self.state.advance_phase(phase_name, "HUMAN_REVIEW")
                    self._save_state()
                    self.logger.log(
                        "phase_completed",
                        phase=phase_name,
                        status="HUMAN_REVIEW",
                    )
                    return PhaseResult(
                        phase_name=phase_name,
                        gate_passed=True,
                        iterations=iterations,
                        requires_human_review=True,
                        gate_report={"overall_pass": True},
                    )
                else:
                    self.state.advance_phase(phase_name, "COMPLETED")
                    self._save_state()
                    self.logger.log(
                        "phase_completed",
                        phase=phase_name,
                        status="COMPLETED",
                    )
                    return PhaseResult(
                        phase_name=phase_name,
                        gate_passed=True,
                        iterations=iterations,
                        gate_report={"overall_pass": True},
                    )
            else:
                # Gates failed -- mark as GATE_FAILED so retry can loop
                self.state.advance_phase(phase_name, "GATE_FAILED")
                self._save_state()

                self.logger.log(
                    "gate_failed",
                    phase=phase_name,
                    iteration=iterations,
                    failures=[r.message for r in report.failures],
                )

                # Clean up result.json so next iteration gets fresh metrics
                for f in self.experiment_dir.rglob("result.json"):
                    f.unlink()

        # Exhausted max_iterations
        self.logger.log(
            "phase_completed",
            phase=phase_name,
            status="GATE_FAILED",
            iterations=iterations,
        )
        return PhaseResult(
            phase_name=phase_name,
            gate_passed=False,
            iterations=iterations,
            gate_report={"overall_pass": False},
        )

    def run_all(self, auto: bool = False) -> list[PhaseResult]:
        """Run phases in order.

        If auto=False: run only the current (first non-completed) phase.
        If auto=True: advance through phases until one requires human review
                      or all are done.
        """
        results: list[PhaseResult] = []

        if not auto:
            current = self.state.get_current_phase()
            if current is not None:
                result = self.run_phase(current.name)
                results.append(result)
            return results

        # auto mode: run phases sequentially
        for phase_config in self.config.phases:
            phase_state = self.state._find_phase(phase_config.name)
            if phase_state.status == "COMPLETED":
                continue

            result = self.run_phase(phase_config.name)
            results.append(result)

            if result.requires_human_review or not result.gate_passed:
                break

        return results

    def check_gates(self, phase_name: str, metrics: dict) -> PhaseGateReport:
        """Evaluate gates for a phase against given metrics. Does not modify state."""
        phase_config = None
        for p in self.config.phases:
            if p.name == phase_name:
                phase_config = p
                break
        if phase_config is None:
            raise ValueError(f"Phase '{phase_name}' not found in config")

        return evaluate_phase_gates(phase_config, metrics)

    def _save_state(self) -> None:
        """Persist state to .scaffold/state.json."""
        self.state.save(self.experiment_dir / ".scaffold" / "state.json")

    def _collect_metrics(self, phase_name: str) -> dict:
        """Collect metrics from result.json files in results directories."""
        metrics: dict = {}
        results_dir = self.experiment_dir / "results"
        for result_file in results_dir.rglob("result.json"):
            try:
                data = json.loads(result_file.read_text())
                if "metrics" in data:
                    metrics.update(data["metrics"])
            except (json.JSONDecodeError, OSError):
                pass
        return metrics
