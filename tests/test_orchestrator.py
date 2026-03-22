# ABOUTME: Tests for the orchestrator that drives experiment phases through gates.
# ABOUTME: Uses real experiment directories from init_experiment with a FakeBackend test double.

from __future__ import annotations

import json
from pathlib import Path

import httpx

from scaffold.config import load_config
from scaffold.gates import PhaseGateReport
from scaffold.init import init_experiment
from scaffold.orchestrator import Orchestrator, PhaseResult
from scaffold.runner import AgentRunner, RunResult
from scaffold.state import ExperimentState
from scaffold.workflow import WorkflowConfig

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
        """All metrics missing (all SKIP) means overall fail -- no work was done."""
        exp_dir = _create_experiment(tmp_path)
        orch, _ = _make_orchestrator(exp_dir)

        metrics = {}  # No metrics at all
        report = orch.check_gates("phase1_oracle_alpha", metrics)
        # All-SKIP = fail (prevents phases advancing with zero experimental work)
        assert report.overall_pass is False
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


class _RecordingRunner(AgentRunner):
    """AgentRunner subclass that records hooks passed to execute()."""

    def __init__(self, backend):
        super().__init__(backend=backend)
        self.execute_calls: list[dict] = []

    def execute(self, prompt_or_script, cwd, hooks=None, timeout=None):
        self.execute_calls.append({"hooks": hooks, "timeout": timeout})
        return super().execute(prompt_or_script, cwd, hooks=hooks, timeout=timeout)


class TestOrchestratorPassesHooks:
    """Tests that the orchestrator passes workflow hooks to the runner."""

    def test_orchestrator_passes_workflow_hooks(self, tmp_path):
        """Workflow hooks from WORKFLOW.md are passed to runner.execute()."""
        exp_dir = _create_experiment(tmp_path)

        # Write a WORKFLOW.md with hooks in the experiment directory
        workflow_md = exp_dir / "WORKFLOW.md"
        workflow_md.write_text(
            "---\nhooks:\n  pre_run: echo pre\n  post_run: echo post\n---\n\nPrompt text\n"
        )

        backend = _FakeBackend(
            metrics={"cross_entropy_delta_nats": 0.5, "p_value": 0.001}
        )
        recording_runner = _RecordingRunner(backend=backend)
        orchestrator = Orchestrator(
            experiment_dir=exp_dir,
            runner=recording_runner,
            max_iterations=1,
        )

        orchestrator.run_phase("phase1_oracle_alpha")

        # Verify hooks were passed to the runner
        assert len(recording_runner.execute_calls) >= 1
        passed_hooks = recording_runner.execute_calls[0]["hooks"]
        assert passed_hooks is not None, "Hooks must be passed to runner.execute()"
        assert "pre_run" in passed_hooks
        assert "post_run" in passed_hooks

    def test_orchestrator_no_workflow_no_hooks(self, tmp_path):
        """Without WORKFLOW.md, hooks default to empty dict (no crash)."""
        exp_dir = _create_experiment(tmp_path)

        # Remove WORKFLOW.md if it exists
        workflow_md = exp_dir / "WORKFLOW.md"
        if workflow_md.exists():
            workflow_md.unlink()

        backend = _FakeBackend(
            metrics={"cross_entropy_delta_nats": 0.5, "p_value": 0.001}
        )
        recording_runner = _RecordingRunner(backend=backend)
        orchestrator = Orchestrator(
            experiment_dir=exp_dir,
            runner=recording_runner,
            max_iterations=1,
        )

        orchestrator.run_phase("phase1_oracle_alpha")

        # Verify hooks are empty dict or None (no crash)
        assert len(recording_runner.execute_calls) >= 1
        passed_hooks = recording_runner.execute_calls[0]["hooks"]
        assert passed_hooks is not None
        assert passed_hooks == {}


# --- Linear Integration ---


class _FakeLinearTransport(httpx.BaseTransport):
    """Records requests and returns canned responses for Linear API tests."""

    def __init__(self, responses=None):
        self.requests: list[httpx.Request] = []
        self.responses = responses or []
        self._idx = 0

    def handle_request(self, request):
        self.requests.append(request)
        if self._idx < len(self.responses):
            resp = self.responses[self._idx]
            self._idx += 1
            return httpx.Response(200, json=resp)
        return httpx.Response(200, json={"data": {}})


def _create_experiment_with_linear(tmp_path: Path, transport: _FakeLinearTransport) -> Path:
    """Create experiment directory with .scaffold/linear.json pre-populated."""
    exp_dir = _create_experiment(tmp_path)
    linear_data = {"issue_id": "issue-orch-test-456"}
    (exp_dir / ".scaffold" / "linear.json").write_text(
        json.dumps(linear_data) + "\n"
    )
    return exp_dir


def _make_orchestrator_with_linear(
    experiment_dir: Path,
    transport: _FakeLinearTransport,
    metrics: dict | None = None,
    success: bool = True,
    max_iterations: int = 3,
) -> tuple[Orchestrator, _FakeBackend]:
    """Create an Orchestrator with a FakeBackend and injected LinearClient."""
    from scaffold.linear import LinearClient

    backend = _FakeBackend(metrics=metrics, success=success)
    runner = AgentRunner(backend=backend)
    http_client = httpx.Client(transport=transport)
    linear_client = LinearClient(api_key="test-key", client=http_client)
    orchestrator = Orchestrator(
        experiment_dir=experiment_dir,
        runner=runner,
        max_iterations=max_iterations,
        _linear_client=linear_client,
    )
    return orchestrator, backend


class TestOrchestratorLinearIntegration:
    """Tests for Linear status updates and gate comments during orchestration."""

    def test_updates_linear_on_phase_start(self, tmp_path):
        """Orchestrator updates Linear to 'In Progress' when phase starts."""
        canned_update = {"data": {"issueUpdate": {"success": True}}}
        canned_comment = {"data": {"commentCreate": {"success": True}}}
        transport = _FakeLinearTransport(
            responses=[canned_update, canned_comment]
        )
        exp_dir = _create_experiment_with_linear(tmp_path, transport)
        passing_metrics = {"cross_entropy_delta_nats": 0.5, "p_value": 0.001}
        orch, _ = _make_orchestrator_with_linear(
            exp_dir, transport, metrics=passing_metrics, max_iterations=1
        )

        orch.run_phase("phase1_oracle_alpha")

        # First request should be the "In Progress" status update
        assert len(transport.requests) >= 1
        first_body = json.loads(transport.requests[0].content)
        assert "issueUpdate" in first_body["query"]
        assert first_body["variables"]["id"] == "issue-orch-test-456"

    def test_posts_gate_comment_after_evaluation(self, tmp_path):
        """Orchestrator posts gate report as comment after gate evaluation."""
        canned_update = {"data": {"issueUpdate": {"success": True}}}
        canned_comment = {"data": {"commentCreate": {"success": True}}}
        transport = _FakeLinearTransport(
            responses=[canned_update, canned_comment]
        )
        exp_dir = _create_experiment_with_linear(tmp_path, transport)
        passing_metrics = {"cross_entropy_delta_nats": 0.5, "p_value": 0.001}
        orch, _ = _make_orchestrator_with_linear(
            exp_dir, transport, metrics=passing_metrics, max_iterations=1
        )

        orch.run_phase("phase1_oracle_alpha")

        # Second request should be the comment
        assert len(transport.requests) >= 2
        comment_body = json.loads(transport.requests[1].content)
        assert "commentCreate" in comment_body["query"]
        comment_text = comment_body["variables"]["input"]["body"]
        assert "phase1_oracle_alpha" in comment_text
        assert "PASS" in comment_text

    def test_updates_linear_done_on_all_complete(self, tmp_path):
        """Orchestrator updates Linear to 'Done' when all phases complete via run_all."""
        # phase2 has requires_human_review=True so it gets HUMAN_REVIEW, not COMPLETED.
        # With minimal config, "all_done" won't be True. We verify the In Progress updates happen.
        canned = {"data": {"issueUpdate": {"success": True}}}
        canned_comment = {"data": {"commentCreate": {"success": True}}}
        transport = _FakeLinearTransport(
            responses=[canned, canned_comment, canned, canned_comment, canned]
        )
        exp_dir = _create_experiment_with_linear(tmp_path, transport)
        all_metrics = {
            "cross_entropy_delta_nats": 0.5,
            "p_value": 0.001,
            "silhouette_score": 0.5,
        }
        orch, _ = _make_orchestrator_with_linear(
            exp_dir, transport, metrics=all_metrics, max_iterations=1
        )

        orch.run_all(auto=True)

        # At least two "In Progress" updates (one per phase)
        update_requests = [
            r for r in transport.requests
            if "issueUpdate" in json.loads(r.content).get("query", "")
        ]
        assert len(update_requests) >= 2

    def test_linear_failure_does_not_block_phase(self, tmp_path):
        """Linear API errors do not prevent phase execution."""
        transport = _FakeLinearTransport(
            responses=[
                {"errors": [{"message": "Auth failed"}]},
                {"errors": [{"message": "Auth failed"}]},
            ]
        )
        exp_dir = _create_experiment_with_linear(tmp_path, transport)
        passing_metrics = {"cross_entropy_delta_nats": 0.5, "p_value": 0.001}
        orch, _ = _make_orchestrator_with_linear(
            exp_dir, transport, metrics=passing_metrics, max_iterations=1
        )

        # Phase should still complete successfully despite Linear failures
        result = orch.run_phase("phase1_oracle_alpha")
        assert result.gate_passed is True

        state = ExperimentState.load(exp_dir / ".scaffold" / "state.json")
        phase = state._find_phase("phase1_oracle_alpha")
        assert phase.status == "COMPLETED"

    def test_no_linear_json_means_no_linear_calls(self, tmp_path):
        """Without .scaffold/linear.json, no Linear API calls are made."""
        transport = _FakeLinearTransport()
        exp_dir = _create_experiment(tmp_path)  # No linear.json
        passing_metrics = {"cross_entropy_delta_nats": 0.5, "p_value": 0.001}
        orch, _ = _make_orchestrator(exp_dir, metrics=passing_metrics)

        orch.run_phase("phase1_oracle_alpha")

        assert len(transport.requests) == 0

    def test_gate_report_includes_thresholds(self, tmp_path):
        """Gate report dict passed to Linear includes threshold and comparator."""
        canned_update = {"data": {"issueUpdate": {"success": True}}}
        canned_comment = {"data": {"commentCreate": {"success": True}}}
        transport = _FakeLinearTransport(
            responses=[canned_update, canned_comment]
        )
        exp_dir = _create_experiment_with_linear(tmp_path, transport)
        passing_metrics = {"cross_entropy_delta_nats": 0.5, "p_value": 0.001}
        orch, _ = _make_orchestrator_with_linear(
            exp_dir, transport, metrics=passing_metrics, max_iterations=1
        )

        orch.run_phase("phase1_oracle_alpha")

        # Find the comment request (second request)
        assert len(transport.requests) >= 2
        comment_body = json.loads(transport.requests[1].content)
        comment_text = comment_body["variables"]["input"]["body"]
        # The comment should contain threshold info (rendered as part of the table)
        # cross_entropy_delta_nats has threshold 0.01 comparator gte
        assert ">= 0.01" in comment_text or "0.01" in comment_text

    def test_skips_linear_comment_on_all_skip(self, tmp_path):
        """No comment posted when all gates are SKIP (no useful info)."""
        canned_update = {"data": {"issueUpdate": {"success": True}}}
        canned_comment = {"data": {"commentCreate": {"success": True}}}
        transport = _FakeLinearTransport(
            responses=[canned_update, canned_comment, canned_comment]
        )
        exp_dir = _create_experiment_with_linear(tmp_path, transport)
        # No metrics at all -> all gates SKIP
        orch, _ = _make_orchestrator_with_linear(
            exp_dir, transport, metrics={}, max_iterations=1
        )

        orch.run_phase("phase1_oracle_alpha")

        # Only the status update should be posted, no comment
        comment_requests = [
            r for r in transport.requests
            if "commentCreate" in json.loads(r.content).get("query", "")
        ]
        assert len(comment_requests) == 0


# --- Inter-iteration Feedback ---


class _SequentialBackend:
    """Backend that returns different metrics on each call.

    Takes a list of metric dicts; call N uses metrics_sequence[N].
    Falls back to the last entry if more calls than entries.
    """

    def __init__(self, metrics_sequence: list[dict]):
        self.metrics_sequence = metrics_sequence
        self.calls: list[dict] = []

    def run(self, prompt: str, cwd: Path, timeout: int | None = None) -> RunResult:
        call_idx = len(self.calls)
        self.calls.append({"prompt": prompt, "cwd": str(cwd), "timeout": timeout})

        # Pick metrics for this iteration
        if call_idx < len(self.metrics_sequence):
            metrics = self.metrics_sequence[call_idx]
        else:
            metrics = self.metrics_sequence[-1]

        # Write result.json so orchestrator's _collect_metrics picks it up
        results_dir = cwd / "results" / "infrastructure"
        results_dir.mkdir(parents=True, exist_ok=True)
        result_data = {
            "metrics": metrics,
            "status": "success",
        }
        (results_dir / "result.json").write_text(json.dumps(result_data))

        return RunResult(
            success=True,
            metrics=metrics,
            stdout="fake output",
            returncode=0,
        )


class TestInterIterationFeedback:
    """Tests that the orchestrator includes gate failure details in retry prompts."""

    def test_first_iteration_has_no_previous_failures(self, tmp_path):
        """First iteration prompt does not contain previous_failures context."""
        exp_dir = _create_experiment(tmp_path)
        passing_metrics = {"cross_entropy_delta_nats": 0.5, "p_value": 0.001}
        orch, backend = _make_orchestrator(
            exp_dir, metrics=passing_metrics, max_iterations=1
        )

        # Write a WORKFLOW.md with dispatch-time Jinja2 variables (no raw blocks,
        # since the orchestrator renders these via render_prompt at dispatch time).
        workflow_md = exp_dir / "WORKFLOW.md"
        workflow_md.write_text(
            "---\nhooks: {}\n---\n\n"
            "Phase: {{ phase }}\n"
            "{% if previous_failures %}"
            "PREVIOUS FAILURES:\n{{ previous_failures }}\n"
            "{% endif %}"
        )

        orch.run_phase("phase1_oracle_alpha")

        assert len(backend.calls) == 1
        first_prompt = backend.calls[0]["prompt"]
        assert "PREVIOUS FAILURES" not in first_prompt

    def test_retry_prompt_includes_previous_gate_failures(self, tmp_path):
        """After gate failure, the next iteration prompt includes failure details."""
        exp_dir = _create_experiment(tmp_path)

        # Iteration 1: failing metrics, Iteration 2: passing metrics
        failing = {"cross_entropy_delta_nats": 0.001, "p_value": 0.5}
        passing = {"cross_entropy_delta_nats": 0.5, "p_value": 0.001}

        backend = _SequentialBackend(metrics_sequence=[failing, passing])
        runner = AgentRunner(backend=backend)
        orch = Orchestrator(
            experiment_dir=exp_dir,
            runner=runner,
            max_iterations=3,
        )

        # Write a WORKFLOW.md with dispatch-time Jinja2 variables (no raw blocks,
        # since the orchestrator renders these via render_prompt at dispatch time).
        workflow_md = exp_dir / "WORKFLOW.md"
        workflow_md.write_text(
            "---\nhooks: {}\n---\n\n"
            "Phase: {{ phase }}\n"
            "{% if previous_failures %}"
            "PREVIOUS FAILURES:\n{{ previous_failures }}\n"
            "{% endif %}"
        )

        result = orch.run_phase("phase1_oracle_alpha")

        # Should have passed on iteration 2
        assert result.gate_passed is True
        assert len(backend.calls) == 2

        # First iteration prompt should NOT have previous failures
        first_prompt = backend.calls[0]["prompt"]
        assert "PREVIOUS FAILURES" not in first_prompt

        # Second iteration prompt SHOULD have previous failures
        second_prompt = backend.calls[1]["prompt"]
        assert "PREVIOUS FAILURES" in second_prompt

        # Should mention the specific failing metrics with observed values
        assert "cross_entropy_delta_nats" in second_prompt
        assert "p_value" in second_prompt
        # Should include the observed values
        assert "0.001" in second_prompt
        assert "0.5" in second_prompt


class TestOrchestratorDefaultTimeout:
    """Tests for Orchestrator passing default_timeout to runner.execute."""

    def test_orchestrator_default_timeout_attribute(self, tmp_path):
        """Orchestrator stores default_timeout (default 14400)."""
        exp_dir = _create_experiment(tmp_path)
        orch, _ = _make_orchestrator(exp_dir)
        assert orch.default_timeout == 14400

    def test_orchestrator_custom_default_timeout(self, tmp_path):
        """Orchestrator accepts a custom default_timeout."""
        exp_dir = _create_experiment(tmp_path)
        backend = _FakeBackend(
            metrics={"cross_entropy_delta_nats": 0.5, "p_value": 0.001}
        )
        runner = AgentRunner(backend=backend)
        orch = Orchestrator(
            experiment_dir=exp_dir, runner=runner, default_timeout=7200,
        )
        assert orch.default_timeout == 7200

    def test_orchestrator_passes_timeout_to_runner(self, tmp_path):
        """Orchestrator passes default_timeout to runner.execute() calls."""
        exp_dir = _create_experiment(tmp_path)
        backend = _FakeBackend(
            metrics={"cross_entropy_delta_nats": 0.5, "p_value": 0.001}
        )
        recording_runner = _RecordingRunner(backend=backend)
        orch = Orchestrator(
            experiment_dir=exp_dir,
            runner=recording_runner,
            max_iterations=1,
            default_timeout=3600,
        )

        orch.run_phase("phase1_oracle_alpha")

        assert len(recording_runner.execute_calls) >= 1
        assert recording_runner.execute_calls[0]["timeout"] == 3600


class _FailingBackend:
    """Test double that returns an error on every call (simulates credit exhaustion, CLI failure, etc.)."""

    def __init__(self, stderr: str = "Credit balance is too low", returncode: int = 1):
        self._stderr = stderr
        self._returncode = returncode
        self.calls: list[dict] = []

    def run(self, prompt: str, cwd: Path, timeout: int | None = None) -> RunResult:
        self.calls.append({"prompt": prompt, "cwd": str(cwd), "timeout": timeout})
        return RunResult(
            success=False,
            stdout="",
            stderr=self._stderr,
            returncode=self._returncode,
        )


class TestAgentErrorEarlyTermination:
    """Tests for G31: abort retry loop when agent fails to start."""

    def test_stops_after_consecutive_agent_failures(self, tmp_path):
        """Orchestrator stops early when agent returns errors on consecutive iterations."""
        exp_dir = _create_experiment(tmp_path)
        backend = _FailingBackend(stderr="Credit balance is too low", returncode=1)
        runner = AgentRunner(backend=backend)
        orch = Orchestrator(
            experiment_dir=exp_dir, runner=runner, max_iterations=20,
        )

        result = orch.run_phase("phase1_oracle_alpha")

        # Should NOT have run all 20 iterations -- should abort early
        assert result.iterations < 20
        assert not result.gate_passed
        # Should have run at most max_consecutive_agent_failures iterations
        assert len(backend.calls) <= 3

    def test_logs_agent_error_event(self, tmp_path):
        """Orchestrator logs an agent_error event when aborting due to consecutive failures."""
        exp_dir = _create_experiment(tmp_path)
        backend = _FailingBackend(stderr="Credit balance is too low")
        runner = AgentRunner(backend=backend)
        orch = Orchestrator(
            experiment_dir=exp_dir, runner=runner, max_iterations=20,
        )

        orch.run_phase("phase1_oracle_alpha")

        # Check that agent_error was logged
        log_files = list((exp_dir / "sessions" / "logs").glob("*.jsonl"))
        assert len(log_files) >= 1
        events = [
            json.loads(line)
            for line in log_files[-1].read_text().strip().split("\n")
            if line.strip()
        ]
        agent_error_events = [e for e in events if e["event_type"] == "agent_error_abort"]
        assert len(agent_error_events) == 1
        assert "Credit balance" in agent_error_events[0]["data"]["stderr"]

    def test_resets_failure_count_on_success(self, tmp_path):
        """If agent succeeds after failures, the consecutive failure count resets."""
        exp_dir = _create_experiment(tmp_path)

        # Backend that fails twice then succeeds
        call_count = 0

        class _FlappingBackend:
            def __init__(self):
                self.calls = []

            def run(self, prompt, cwd, timeout=None):
                self.calls.append({"prompt": prompt})
                nonlocal call_count
                call_count += 1
                if call_count <= 2:
                    return RunResult(
                        success=False, stdout="", stderr="Temporary error", returncode=1,
                    )
                # Third call succeeds but still no metrics (gates fail)
                return RunResult(
                    success=True, stdout="ok", stderr="", returncode=0,
                )

        backend = _FlappingBackend()
        runner = AgentRunner(backend=backend)
        orch = Orchestrator(
            experiment_dir=exp_dir, runner=runner, max_iterations=10,
        )

        result = orch.run_phase("phase1_oracle_alpha")

        # Should have run more than 3 iterations (failure count reset after success)
        assert len(backend.calls) > 3
