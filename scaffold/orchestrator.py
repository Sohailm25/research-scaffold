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
from scaffold.state import ExperimentState, _now_iso
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
        _linear_client: object | None = None,
        default_timeout: int = 14400,
    ):
        self.experiment_dir = experiment_dir
        self.runner = runner
        self.max_iterations = max_iterations
        self.default_timeout = default_timeout

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

        # Load Linear issue ID if available
        self._linear_issue_id = None
        self._linear_client = _linear_client
        linear_json = experiment_dir / ".scaffold" / "linear.json"
        if linear_json.exists():
            try:
                data = json.loads(linear_json.read_text())
                self._linear_issue_id = data.get("issue_id")
                if self._linear_client is None:
                    from scaffold.linear import LinearClient
                    self._linear_client = LinearClient()
            except Exception:
                pass

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
        previous_failures = ""
        consecutive_agent_failures = 0
        max_consecutive_agent_failures = 3

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

            # Update Linear status
            if iterations == 1 and self._linear_client and self._linear_issue_id:
                try:
                    self._linear_client.update_experiment_status(
                        self._linear_issue_id, "In Progress"
                    )
                except Exception:
                    pass

            # Build prompt
            prompt = phase_name
            if workflow is not None:
                # Build gates display for the agent
                gates_lines = []
                for g in phase_config.gates:
                    gates_lines.append(
                        f"- `{g.metric}` {g.comparator} {g.threshold}"
                    )
                gates_display = "\n".join(gates_lines) if gates_lines else "No gates defined for this phase."

                # Load completed phase summaries for inter-phase context
                completed_phases = []
                summaries_dir = self.experiment_dir / ".scaffold" / "phase_summaries"
                if summaries_dir.exists():
                    for summary_file in sorted(summaries_dir.glob("*.json")):
                        try:
                            summary = json.loads(summary_file.read_text())
                            completed_phases.append(summary)
                        except (json.JSONDecodeError, OSError):
                            pass

                context = {
                    "phase": phase_name,
                    "lane": phase_config.name,
                    "task": phase_config.description,
                    "gates_display": gates_display,
                    "iteration": iterations,
                    "max_iterations": self.max_iterations,
                    "previous_failures": previous_failures,
                    "phase_type": phase_config.phase_type,
                    "completed_phases": completed_phases,
                    "random_seed": self.config.random_seed,
                }
                try:
                    prompt = render_prompt(workflow, context)
                except Exception:
                    prompt = phase_name

            # Extract hooks from workflow
            workflow_hooks = workflow.hooks if workflow is not None else {}

            # Dispatch to runner
            try:
                run_result = self.runner.execute(
                    prompt, cwd=self.experiment_dir, hooks=workflow_hooks,
                    timeout=self.default_timeout,
                )
            except Exception as exc:
                self.logger.log(
                    "run_error", phase=phase_name, error=str(exc)
                )
                run_result = RunResult(
                    success=False, stderr=str(exc), returncode=-1
                )

            # Track consecutive agent failures for early termination
            if not run_result.success and run_result.returncode != 0:
                consecutive_agent_failures += 1
                if consecutive_agent_failures >= max_consecutive_agent_failures:
                    self.logger.log(
                        "agent_error_abort",
                        phase=phase_name,
                        iteration=iterations,
                        consecutive_failures=consecutive_agent_failures,
                        stderr=run_result.stderr[:500] if run_result.stderr else "",
                    )
                    # Advance through required states before returning
                    self.state.advance_phase(phase_name, "GATE_CHECK")
                    self.state.advance_phase(phase_name, "GATE_FAILED")
                    self._save_state()
                    return PhaseResult(
                        phase_name=phase_name,
                        gate_passed=False,
                        iterations=iterations,
                        gate_report={"overall_pass": False, "agent_error": True},
                    )
            else:
                consecutive_agent_failures = 0

            # Advance to GATE_CHECK
            self.state.advance_phase(phase_name, "GATE_CHECK")
            self._save_state()

            # Collect metrics and evaluate gates
            metrics = self._collect_metrics(phase_name, run_result)
            report = evaluate_phase_gates(phase_config, metrics)

            self.logger.log(
                "gate_evaluated",
                phase=phase_name,
                overall_pass=report.overall_pass,
                iteration=iterations,
            )

            # Record metrics snapshot in phase history
            phase_state = self.state._find_phase(phase_name)
            phase_state.metrics_history.append({
                "iteration": iterations,
                "timestamp": _now_iso(),
                "metrics": dict(metrics),
                "gate_passed": report.overall_pass,
            })

            # Post gate report to Linear
            if self._linear_client and self._linear_issue_id:
                try:
                    gate_report_dict = {
                        "overall_pass": report.overall_pass,
                        "results": [
                            {
                                "metric": r.gate.metric,
                                "status": r.status,
                                "observed_value": r.observed_value,
                                "threshold": r.gate.threshold,
                                "comparator": r.gate.comparator,
                            }
                            for r in report.results
                        ],
                    }
                    gate_results = gate_report_dict["results"]
                    all_skip = len(gate_results) > 0 and all(
                        r["status"] == "SKIP" for r in gate_results
                    )
                    if not all_skip and len(gate_results) > 0:
                        self._linear_client.add_phase_comment(
                            self._linear_issue_id, phase_name, gate_report_dict,
                            iteration=iterations,
                            max_iterations=self.max_iterations,
                            phase_states=[
                                {"name": ps.name, "status": ps.status}
                                for ps in self.state.phases
                            ],
                        )
                except Exception:
                    pass

            if report.overall_pass:
                # Gates passed
                self.state.advance_phase(phase_name, "GATE_PASSED")
                self._save_state()

                # Write phase summary for inter-phase context
                summary = {
                    "phase_name": phase_name,
                    "iterations": iterations,
                    "metrics": dict(metrics),
                    "gate_passed": True,
                    "timestamp": _now_iso(),
                }
                summaries_dir = self.experiment_dir / ".scaffold" / "phase_summaries"
                summaries_dir.mkdir(parents=True, exist_ok=True)
                (summaries_dir / f"{phase_name}.json").write_text(
                    json.dumps(summary, indent=2) + "\n"
                )

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

                # Build feedback for next iteration so the agent knows what failed
                failure_lines = []
                for r in report.results:
                    if r.status == "FAIL":
                        failure_lines.append(
                            f"- {r.gate.metric}: observed={r.observed_value}, "
                            f"required {r.gate.comparator} {r.gate.threshold}"
                        )
                    elif r.status == "SKIP":
                        failure_lines.append(
                            f"- {r.gate.metric}: MISSING (required {r.gate.comparator} {r.gate.threshold})"
                        )
                near_miss_lines = []
                for r in report.results:
                    if r.status == "FAIL" and r.near_miss:
                        near_miss_lines.append(
                            f"- {r.gate.metric}: observed={r.observed_value} "
                            f"(within 10% of threshold {r.gate.threshold})"
                        )
                if near_miss_lines:
                    failure_lines.append("")
                    failure_lines.append("**Near misses** (consider minor adjustments, not major overhaul):")
                    failure_lines.extend(near_miss_lines)
                if failure_lines:
                    previous_failures = (
                        f"Iteration {iterations} gate failures:\n"
                        + "\n".join(failure_lines)
                    )

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

        # Update Linear to Done if all phases completed
        if self._linear_client and self._linear_issue_id:
            all_done = all(
                self.state._find_phase(p.name).status == "COMPLETED"
                for p in self.config.phases
            )
            if all_done:
                try:
                    self._linear_client.update_experiment_status(
                        self._linear_issue_id, "Done"
                    )
                except Exception:
                    pass

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

    def _collect_metrics(self, phase_name: str, run_result: RunResult | None = None) -> dict:
        """Collect metrics from result.json files and RunResult.

        Searches three sources (later sources override earlier):
        1. result.json files in results/ subdirectories
        2. result.json in the experiment root directory
        3. RunResult.metrics from the runner (if provided)
        """
        metrics: dict = {}

        # 1. Search results/ subdirectories
        results_dir = self.experiment_dir / "results"
        for result_file in results_dir.rglob("result.json"):
            try:
                data = json.loads(result_file.read_text())
                if "metrics" in data:
                    metrics.update(data["metrics"])
            except (json.JSONDecodeError, OSError):
                pass

        # 2. Check experiment root
        root_result = self.experiment_dir / "result.json"
        if root_result.exists():
            try:
                data = json.loads(root_result.read_text())
                if "metrics" in data:
                    metrics.update(data["metrics"])
            except (json.JSONDecodeError, OSError):
                pass

        # 3. Merge RunResult metrics (highest priority)
        if run_result is not None and run_result.metrics:
            metrics.update(run_result.metrics)

        return metrics
