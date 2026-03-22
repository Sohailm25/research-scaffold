# ABOUTME: Tests for the orchestrator that drives experiment phases through gates.
# ABOUTME: Uses real experiment directories from init_experiment with a FakeBackend test double.

from __future__ import annotations

import json
from pathlib import Path

from scaffold.config import load_config
from scaffold.gates import PhaseGateReport
from scaffold.init import init_experiment
from scaffold.orchestrator import Orchestrator, PhaseResult
from scaffold.runner import AgentRunner, RunResult
from scaffold.state import ExperimentState

_FIXTURE_CONFIG = Path(__file__).parent / "fixtures" / "minimal_config.yaml"


class _FakeBackend:
    """Test double that writes controlled result.json files for the orchestrator to find."""

    def __init__(self, metrics: dict | None = None, success: bool = True):
        self.metrics = metrics or {}
        self.success = success
        self.calls: list[dict] = []

    def run(self, prompt: str, cwd: Path, timeout: int | None = None) -> RunResult:
        self.calls.append({"prompt": prompt, "cwd": str(cwd), "timeout": timeout})

        # Write result.json so orchestrator's _collect_metrics picks it up
        results_dir = cwd / "results" / "infrastructure"
        results_dir.mkdir(parents=True, exist_ok=True)
        result_data = {
            "metrics": self.metrics,
            "status": "success" if self.success else "failure",
        }
        (results_dir / "result.json").write_text(json.dumps(result_data))

        return RunResult(
            success=self.success,
            metrics=self.metrics,
            stdout="fake output",
            returncode=0 if self.success else 1,
        )


def _create_experiment(tmp_path: Path) -> Path:
    """Create a minimal experiment directory for testing.

    The init system renders a template experiment.yaml with a different schema
    than load_config expects. We overwrite it with the original fixture so the
    orchestrator can load it through the standard config loader.
    """
    config = load_config(_FIXTURE_CONFIG)
    exp_dir = init_experiment(config, tmp_path, skip_external=True)

    # Overwrite rendered template with the original flat-schema config
    import shutil
    shutil.copy(_FIXTURE_CONFIG, exp_dir / "configs" / "experiment.yaml")

    return exp_dir


def _make_orchestrator(
    experiment_dir: Path,
    metrics: dict | None = None,
    success: bool = True,
    max_iterations: int = 3,
) -> tuple[Orchestrator, _FakeBackend]:
    """Create an Orchestrator with a FakeBackend for testing."""
    backend = _FakeBackend(metrics=metrics, success=success)
    runner = AgentRunner(backend=backend)
    orchestrator = Orchestrator(
        experiment_dir=experiment_dir,
        runner=runner,
        max_iterations=max_iterations,
    )
    return orchestrator, backend


class TestPhaseResult:
    """Tests for PhaseResult dataclass defaults."""

    def test_phase_result_defaults(self):
        """PhaseResult has sensible defaults for optional fields."""
        result = PhaseResult(phase_name="phase1", gate_passed=True)
        assert result.phase_name == "phase1"
        assert result.gate_passed is True
        assert result.negative_result is False
        assert result.iterations == 0
        assert result.requires_human_review is False
        assert result.gate_report is None


class TestOrchestratorInit:
    """Tests for Orchestrator initialization from experiment directory."""

    def test_loads_config_and_state(self, tmp_path):
        """Orchestrator reads config and state from experiment directory."""
        exp_dir = _create_experiment(tmp_path)
        orch, _ = _make_orchestrator(exp_dir)
        assert orch.config.name == "test-experiment"
        assert orch.state.experiment_name == "test-experiment"
        assert len(orch.state.phases) == 2

    def test_creates_session_logger(self, tmp_path):
        """Orchestrator initializes a session logger."""
        exp_dir = _create_experiment(tmp_path)
        orch, _ = _make_orchestrator(exp_dir)
        assert orch.logger is not None
        assert orch.logger.session_id.startswith("orchestrator-")


class TestCollectMetrics:
    """Tests for _collect_metrics reading result.json files."""

    def test_collect_metrics_from_result_json(self, tmp_path):
        """Collects metrics from result.json in results/ subdirectories."""
        exp_dir = _create_experiment(tmp_path)
        orch, _ = _make_orchestrator(exp_dir)

        # Write a result.json with metrics
        results_dir = exp_dir / "results" / "infrastructure"
        results_dir.mkdir(parents=True, exist_ok=True)
        (results_dir / "result.json").write_text(
            json.dumps({"metrics": {"accuracy": 0.95, "loss": 0.1}})
        )

        metrics = orch._collect_metrics("phase1")
        assert metrics["accuracy"] == 0.95
        assert metrics["loss"] == 0.1

    def test_collect_metrics_no_files(self, tmp_path):
        """Returns empty dict when no result.json files exist."""
        exp_dir = _create_experiment(tmp_path)
        orch, _ = _make_orchestrator(exp_dir)

        # Remove any pre-existing result.json
        for f in exp_dir.rglob("result.json"):
            f.unlink()

        metrics = orch._collect_metrics("phase1")
        assert metrics == {}

    def test_collect_metrics_merges_multiple(self, tmp_path):
        """Multiple result.json files have their metrics merged."""
        exp_dir = _create_experiment(tmp_path)
        orch, _ = _make_orchestrator(exp_dir)

        dir_a = exp_dir / "results" / "lane_a"
        dir_a.mkdir(parents=True, exist_ok=True)
        (dir_a / "result.json").write_text(
            json.dumps({"metrics": {"metric_a": 1.0}})
        )

        dir_b = exp_dir / "results" / "lane_b"
        dir_b.mkdir(parents=True, exist_ok=True)
        (dir_b / "result.json").write_text(
            json.dumps({"metrics": {"metric_b": 2.0}})
        )

        metrics = orch._collect_metrics("phase1")
        assert metrics["metric_a"] == 1.0
        assert metrics["metric_b"] == 2.0


class TestCheckGates:
    """Tests for check_gates evaluating metrics against phase thresholds."""

    def test_check_gates_pass(self, tmp_path):
        """Metrics meeting all thresholds produce overall_pass=True."""
        exp_dir = _create_experiment(tmp_path)
        orch, _ = _make_orchestrator(exp_dir)

        # phase1_oracle_alpha has: cross_entropy_delta_nats gte 0.01, p_value lte 0.01
        metrics = {"cross_entropy_delta_nats": 0.5, "p_value": 0.001}
        report = orch.check_gates("phase1_oracle_alpha", metrics)
        assert isinstance(report, PhaseGateReport)
        assert report.overall_pass is True

    def test_check_gates_fail(self, tmp_path):
        """Metrics below thresholds produce overall_pass=False."""
        exp_dir = _create_experiment(tmp_path)
        orch, _ = _make_orchestrator(exp_dir)

        metrics = {"cross_entropy_delta_nats": 0.001, "p_value": 0.5}
        report = orch.check_gates("phase1_oracle_alpha", metrics)
        assert report.overall_pass is False
        assert len(report.failures) > 0

    def test_check_gates_skip(self, tmp_path):
        """Missing metrics produce SKIP results (not failure)."""
        exp_dir = _create_experiment(tmp_path)
        orch, _ = _make_orchestrator(exp_dir)

        metrics = {}  # No metrics at all
        report = orch.check_gates("phase1_oracle_alpha", metrics)
        # SKIP does not cause failure per the gate evaluation logic
        assert report.overall_pass is True
        assert all(r.status == "SKIP" for r in report.results)


class TestRunPhase:
    """Tests for run_phase executing a single phase with gate evaluation."""

    def test_run_phase_gates_pass(self, tmp_path):
        """Phase with passing metrics advances to COMPLETED."""
        exp_dir = _create_experiment(tmp_path)
        passing_metrics = {"cross_entropy_delta_nats": 0.5, "p_value": 0.001}
        orch, backend = _make_orchestrator(exp_dir, metrics=passing_metrics)

        result = orch.run_phase("phase1_oracle_alpha")
        assert result.gate_passed is True
        assert result.phase_name == "phase1_oracle_alpha"

        # Verify state was updated
        state = ExperimentState.load(exp_dir / ".scaffold" / "state.json")
        phase = state._find_phase("phase1_oracle_alpha")
        assert phase.status == "COMPLETED"

    def test_run_phase_gates_fail_retries(self, tmp_path):
        """Phase with failing metrics retries until max_iterations."""
        exp_dir = _create_experiment(tmp_path)
        failing_metrics = {"cross_entropy_delta_nats": 0.001, "p_value": 0.5}
        orch, backend = _make_orchestrator(
            exp_dir, metrics=failing_metrics, max_iterations=2
        )

        result = orch.run_phase("phase1_oracle_alpha")
        assert result.gate_passed is False
        # Should have tried max_iterations times
        assert len(backend.calls) == 2

    def test_run_phase_max_iterations(self, tmp_path):
        """Phase stops retrying at max_iterations."""
        exp_dir = _create_experiment(tmp_path)
        failing_metrics = {"cross_entropy_delta_nats": 0.001, "p_value": 0.5}
        orch, backend = _make_orchestrator(
            exp_dir, metrics=failing_metrics, max_iterations=3
        )

        result = orch.run_phase("phase1_oracle_alpha")
        assert result.gate_passed is False
        assert result.iterations == 3
        assert len(backend.calls) == 3

    def test_run_phase_updates_state(self, tmp_path):
        """State.json is persisted after phase execution."""
        exp_dir = _create_experiment(tmp_path)
        passing_metrics = {"cross_entropy_delta_nats": 0.5, "p_value": 0.001}
        orch, _ = _make_orchestrator(exp_dir, metrics=passing_metrics)

        orch.run_phase("phase1_oracle_alpha")

        # Reload state from disk and verify
        state = ExperimentState.load(exp_dir / ".scaffold" / "state.json")
        phase = state._find_phase("phase1_oracle_alpha")
        assert phase.status == "COMPLETED"

    def test_run_phase_logs_events(self, tmp_path):
        """Session logger captures phase events."""
        exp_dir = _create_experiment(tmp_path)
        passing_metrics = {"cross_entropy_delta_nats": 0.5, "p_value": 0.001}
        orch, _ = _make_orchestrator(exp_dir, metrics=passing_metrics)

        orch.run_phase("phase1_oracle_alpha")

        events = orch.logger.read_events()
        event_types = [e.event_type for e in events]
        assert "phase_started" in event_types
        assert "phase_completed" in event_types

    def test_run_phase_human_review(self, tmp_path):
        """Phase with requires_human_review pauses at HUMAN_REVIEW."""
        exp_dir = _create_experiment(tmp_path)
        # phase2_pattern_analysis has requires_human_review=true
        # First complete phase1 so phase2 can run
        passing_metrics1 = {"cross_entropy_delta_nats": 0.5, "p_value": 0.001}
        orch, backend = _make_orchestrator(exp_dir, metrics=passing_metrics1)
        orch.run_phase("phase1_oracle_alpha")

        # Now run phase2 with passing metrics (silhouette_score gte 0.2)
        backend.metrics = {"silhouette_score": 0.5}
        result = orch.run_phase("phase2_pattern_analysis")
        assert result.requires_human_review is True

        state = ExperimentState.load(exp_dir / ".scaffold" / "state.json")
        phase = state._find_phase("phase2_pattern_analysis")
        assert phase.status == "HUMAN_REVIEW"


class TestRunAll:
    """Tests for run_all executing multiple phases."""

    def test_run_all_single_phase(self, tmp_path):
        """auto=False runs only the current (first non-completed) phase."""
        exp_dir = _create_experiment(tmp_path)
        passing_metrics = {"cross_entropy_delta_nats": 0.5, "p_value": 0.001}
        orch, backend = _make_orchestrator(exp_dir, metrics=passing_metrics)

        results = orch.run_all(auto=False)
        assert len(results) == 1
        assert results[0].phase_name == "phase1_oracle_alpha"

    def test_run_all_auto_advances(self, tmp_path):
        """auto=True advances through multiple phases."""
        exp_dir = _create_experiment(tmp_path)
        # Provide metrics that pass both phases
        all_metrics = {
            "cross_entropy_delta_nats": 0.5,
            "p_value": 0.001,
            "silhouette_score": 0.5,
        }
        orch, backend = _make_orchestrator(exp_dir, metrics=all_metrics)

        results = orch.run_all(auto=True)
        # Phase 2 has requires_human_review=True so it stops there
        assert len(results) >= 1
        assert results[0].phase_name == "phase1_oracle_alpha"
        assert results[0].gate_passed is True

    def test_run_all_stops_at_human_review(self, tmp_path):
        """auto=True stops when encountering a phase requiring human review."""
        exp_dir = _create_experiment(tmp_path)
        all_metrics = {
            "cross_entropy_delta_nats": 0.5,
            "p_value": 0.001,
            "silhouette_score": 0.5,
        }
        orch, _ = _make_orchestrator(exp_dir, metrics=all_metrics)

        results = orch.run_all(auto=True)
        # Phase2 has requires_human_review=True
        human_review_results = [r for r in results if r.requires_human_review]
        assert len(human_review_results) == 1
        assert human_review_results[0].phase_name == "phase2_pattern_analysis"
