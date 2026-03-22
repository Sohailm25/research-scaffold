# ABOUTME: Tests for the Click CLI entry point covering init, run, status, gate-check, and approve.
# ABOUTME: Uses CliRunner for isolated CLI testing with real experiment directories.

from __future__ import annotations

import json
import shutil
from pathlib import Path

from click.testing import CliRunner

from scaffold.cli import main
from scaffold.config import load_config
from scaffold.init import init_experiment
from scaffold.state import ExperimentState

_FIXTURE_CONFIG = Path(__file__).parent / "fixtures" / "minimal_config.yaml"


def _create_experiment(tmp_path: Path) -> Path:
    """Create a minimal experiment directory for CLI testing.

    Overwrites the template-rendered experiment.yaml with the original
    flat-schema fixture so the orchestrator can load it.
    """
    config = load_config(_FIXTURE_CONFIG)
    exp_dir = init_experiment(config, tmp_path, skip_external=True)
    shutil.copy(_FIXTURE_CONFIG, exp_dir / "configs" / "experiment.yaml")
    return exp_dir


class TestMainGroup:
    def test_help_shows_commands(self):
        runner = CliRunner()
        result = runner.invoke(main, ["--help"])
        assert result.exit_code == 0
        assert "init" in result.output
        assert "run" in result.output
        assert "status" in result.output
        assert "gate-check" in result.output
        assert "approve" in result.output


class TestInitCommand:
    def test_init_with_config(self, tmp_path: Path):
        runner = CliRunner()
        result = runner.invoke(main, [
            "init", "my-experiment",
            "--root", str(tmp_path),
            "--config", str(_FIXTURE_CONFIG),
        ])
        assert result.exit_code == 0
        assert "Experiment initialized at:" in result.output
        exp_dir = tmp_path / "my-experiment"
        assert exp_dir.exists()

    def test_init_without_config_errors(self, tmp_path: Path):
        runner = CliRunner()
        result = runner.invoke(main, [
            "init", "my-experiment",
            "--root", str(tmp_path),
        ])
        assert result.exit_code != 0
        assert "Error" in result.output or "--config is required" in result.output

    def test_init_shows_path(self, tmp_path: Path):
        runner = CliRunner()
        result = runner.invoke(main, [
            "init", "path-test",
            "--root", str(tmp_path),
            "--config", str(_FIXTURE_CONFIG),
        ])
        assert result.exit_code == 0
        expected_path = str(tmp_path / "path-test")
        assert expected_path in result.output


class TestStatusCommand:
    def test_status_shows_experiment_name(self, tmp_path: Path):
        exp_dir = _create_experiment(tmp_path)
        runner = CliRunner()
        result = runner.invoke(main, ["status", "-e", str(exp_dir)])
        assert result.exit_code == 0
        assert "test-experiment" in result.output

    def test_status_shows_phases(self, tmp_path: Path):
        exp_dir = _create_experiment(tmp_path)
        runner = CliRunner()
        result = runner.invoke(main, ["status", "-e", str(exp_dir)])
        assert result.exit_code == 0
        assert "phase1_oracle_alpha" in result.output
        assert "phase2_pattern_analysis" in result.output
        assert "NOT_STARTED" in result.output


class TestGateCheckCommand:
    def test_gate_check_shows_results(self, tmp_path: Path):
        exp_dir = _create_experiment(tmp_path)

        # Write a result.json with metrics that will pass gates
        results_dir = exp_dir / "results" / "infrastructure"
        results_dir.mkdir(parents=True, exist_ok=True)
        result_data = {
            "metrics": {
                "cross_entropy_delta_nats": 0.05,
                "p_value": 0.001,
            }
        }
        (results_dir / "result.json").write_text(json.dumps(result_data))

        runner = CliRunner()
        result = runner.invoke(main, [
            "gate-check", "-e", str(exp_dir), "-p", "phase1_oracle_alpha",
        ])
        assert result.exit_code == 0
        assert "phase1_oracle_alpha" in result.output
        assert "PASS" in result.output

    def test_gate_check_unknown_phase(self, tmp_path: Path):
        exp_dir = _create_experiment(tmp_path)
        runner = CliRunner()
        result = runner.invoke(main, [
            "gate-check", "-e", str(exp_dir), "-p", "nonexistent_phase",
        ])
        assert result.exit_code != 0


class TestApproveCommand:
    def test_approve_from_human_review(self, tmp_path: Path):
        exp_dir = _create_experiment(tmp_path)
        state_path = exp_dir / ".scaffold" / "state.json"
        state = ExperimentState.load(state_path)

        # Manually advance phase2 to HUMAN_REVIEW
        state.advance_phase("phase2_pattern_analysis", "IN_PROGRESS")
        state.advance_phase("phase2_pattern_analysis", "GATE_CHECK")
        state.advance_phase("phase2_pattern_analysis", "GATE_PASSED")
        state.advance_phase("phase2_pattern_analysis", "HUMAN_REVIEW")
        state.save(state_path)

        runner = CliRunner()
        result = runner.invoke(main, [
            "approve", "-e", str(exp_dir), "-p", "phase2_pattern_analysis",
        ])
        assert result.exit_code == 0
        assert "COMPLETED" in result.output

        # Verify state was actually persisted
        reloaded = ExperimentState.load(state_path)
        phase = reloaded._find_phase("phase2_pattern_analysis")
        assert phase.status == "COMPLETED"

    def test_approve_wrong_status(self, tmp_path: Path):
        exp_dir = _create_experiment(tmp_path)
        runner = CliRunner()
        result = runner.invoke(main, [
            "approve", "-e", str(exp_dir), "-p", "phase1_oracle_alpha",
        ])
        # Phase is NOT_STARTED, not HUMAN_REVIEW, should error
        assert result.exit_code != 0
        assert "NOT_STARTED" in result.output or "not HUMAN_REVIEW" in result.output


# --- cleanup-experiments ---


class TestCleanupExperiments:
    def test_dry_run_lists_issues_by_state(self, monkeypatch):
        """Default mode (no --cancel-state) lists issues grouped by state."""
        fake_issues = [
            {"id": "id-1", "title": "test-experiment", "state": "Todo",
             "description": "", "created_at": "", "updated_at": ""},
            {"id": "id-2", "title": "real-experiment", "state": "In Progress",
             "description": "", "created_at": "", "updated_at": ""},
            {"id": "id-3", "title": "path-test", "state": "Todo",
             "description": "", "created_at": "", "updated_at": ""},
        ]
        monkeypatch.setattr(
            "scaffold.linear.LinearClient",
            lambda: type("MockClient", (), {"list_experiments": lambda self: fake_issues})(),
        )

        runner = CliRunner()
        result = runner.invoke(main, ["cleanup-experiments"])
        assert result.exit_code == 0
        assert "Todo: 2" in result.output
        assert "In Progress: 1" in result.output
        assert "test-experiment" in result.output

    def test_cancel_state_cancels_matching_issues(self, monkeypatch):
        """--cancel-state Todo cancels all Todo issues."""
        fake_issues = [
            {"id": "id-1", "title": "test-experiment", "state": "Todo",
             "description": "", "created_at": "", "updated_at": ""},
            {"id": "id-2", "title": "real-experiment", "state": "In Progress",
             "description": "", "created_at": "", "updated_at": ""},
            {"id": "id-3", "title": "path-test", "state": "Todo",
             "description": "", "created_at": "", "updated_at": ""},
        ]
        canceled_ids = []

        class MockClient:
            def list_experiments(self):
                return fake_issues
            def update_experiment_status(self, issue_id, state):
                canceled_ids.append((issue_id, state))

        monkeypatch.setattr("scaffold.linear.LinearClient", lambda: MockClient())

        runner = CliRunner()
        result = runner.invoke(main, ["cleanup-experiments", "--cancel-state", "Todo"], input="y\n")
        assert result.exit_code == 0
        assert len(canceled_ids) == 2
        assert all(state == "Canceled" for _, state in canceled_ids)
        assert {id for id, _ in canceled_ids} == {"id-1", "id-3"}

    def test_cancel_state_aborts_on_no(self, monkeypatch):
        """User declining cancellation does not cancel anything."""
        fake_issues = [
            {"id": "id-1", "title": "test-experiment", "state": "Todo",
             "description": "", "created_at": "", "updated_at": ""},
        ]
        canceled_ids = []

        class MockClient:
            def list_experiments(self):
                return fake_issues
            def update_experiment_status(self, issue_id, state):
                canceled_ids.append(issue_id)

        monkeypatch.setattr("scaffold.linear.LinearClient", lambda: MockClient())

        runner = CliRunner()
        result = runner.invoke(main, ["cleanup-experiments", "--cancel-state", "Todo"], input="n\n")
        assert result.exit_code == 0
        assert len(canceled_ids) == 0
        assert "Aborted" in result.output
