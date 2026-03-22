# ABOUTME: Tests for experiment state machine and JSON persistence.
# ABOUTME: Covers phase transitions, serialization, and state lifecycle.

import json
from pathlib import Path

import pytest

from scaffold.state import ExperimentState, PhaseState


class TestPhaseState:
    """Tests for the PhaseState dataclass."""

    def test_default_values(self):
        ps = PhaseState(name="phase1")
        assert ps.name == "phase1"
        assert ps.status == "NOT_STARTED"
        assert ps.iteration_count == 0
        assert ps.metrics == {}

    def test_custom_values(self):
        ps = PhaseState(name="phase2", status="IN_PROGRESS", iteration_count=3, metrics={"acc": 0.9})
        assert ps.status == "IN_PROGRESS"
        assert ps.iteration_count == 3
        assert ps.metrics["acc"] == 0.9


class TestExperimentState:
    """Tests for the ExperimentState dataclass."""

    def test_default_values(self):
        state = ExperimentState(experiment_name="test-exp")
        assert state.experiment_name == "test-exp"
        assert state.status == "PLANNING"
        assert state.phases == []
        assert state.current_phase is None
        assert state.created_at is not None
        assert state.updated_at is not None

    def test_timestamps_are_iso_format(self):
        state = ExperimentState(experiment_name="test-exp")
        # Should be parseable as ISO timestamp (contains T and has digits)
        assert "T" in state.created_at or state.created_at.count("-") >= 2
        # Both timestamps set on creation
        assert state.created_at == state.updated_at


class TestExperimentStateFromConfig:
    """Tests for creating ExperimentState from config."""

    def test_from_config_creates_phases(self):
        from scaffold.config import PhaseConfig

        phases = [
            PhaseConfig(name="phase1", description="First phase"),
            PhaseConfig(name="phase2", description="Second phase", depends_on=["phase1"]),
        ]

        class MockConfig:
            name = "test-experiment"

        mock_config = MockConfig()
        mock_config.phases = phases

        state = ExperimentState.from_config(mock_config)
        assert state.experiment_name == "test-experiment"
        assert len(state.phases) == 2
        assert state.phases[0].name == "phase1"
        assert state.phases[0].status == "NOT_STARTED"
        assert state.phases[1].name == "phase2"
        assert state.phases[1].status == "NOT_STARTED"

    def test_from_config_sets_planning_status(self):
        from scaffold.config import PhaseConfig

        class MockConfig:
            name = "my-exp"
            phases = [PhaseConfig(name="p1", description="desc")]

        state = ExperimentState.from_config(MockConfig())
        assert state.status == "PLANNING"


class TestPhaseTransitions:
    """Tests for valid and invalid phase transitions."""

    def _make_state_with_phase(self, phase_name="phase1", initial_status="NOT_STARTED"):
        ps = PhaseState(name=phase_name, status=initial_status)
        return ExperimentState(experiment_name="test", phases=[ps])

    def test_not_started_to_in_progress(self):
        state = self._make_state_with_phase()
        state.advance_phase("phase1", "IN_PROGRESS")
        assert state.phases[0].status == "IN_PROGRESS"

    def test_in_progress_to_gate_check(self):
        state = self._make_state_with_phase(initial_status="IN_PROGRESS")
        state.advance_phase("phase1", "GATE_CHECK")
        assert state.phases[0].status == "GATE_CHECK"

    def test_gate_check_to_gate_passed(self):
        state = self._make_state_with_phase(initial_status="GATE_CHECK")
        state.advance_phase("phase1", "GATE_PASSED")
        assert state.phases[0].status == "GATE_PASSED"

    def test_gate_check_to_gate_failed(self):
        state = self._make_state_with_phase(initial_status="GATE_CHECK")
        state.advance_phase("phase1", "GATE_FAILED")
        assert state.phases[0].status == "GATE_FAILED"

    def test_gate_check_to_negative_result(self):
        state = self._make_state_with_phase(initial_status="GATE_CHECK")
        state.advance_phase("phase1", "NEGATIVE_RESULT")
        assert state.phases[0].status == "NEGATIVE_RESULT"

    def test_gate_passed_to_human_review(self):
        state = self._make_state_with_phase(initial_status="GATE_PASSED")
        state.advance_phase("phase1", "HUMAN_REVIEW")
        assert state.phases[0].status == "HUMAN_REVIEW"

    def test_gate_passed_to_completed(self):
        state = self._make_state_with_phase(initial_status="GATE_PASSED")
        state.advance_phase("phase1", "COMPLETED")
        assert state.phases[0].status == "COMPLETED"

    def test_gate_failed_to_in_progress_retry(self):
        state = self._make_state_with_phase(initial_status="GATE_FAILED")
        state.advance_phase("phase1", "IN_PROGRESS")
        assert state.phases[0].status == "IN_PROGRESS"

    def test_human_review_to_completed(self):
        state = self._make_state_with_phase(initial_status="HUMAN_REVIEW")
        state.advance_phase("phase1", "COMPLETED")
        assert state.phases[0].status == "COMPLETED"

    def test_negative_result_to_completed(self):
        state = self._make_state_with_phase(initial_status="NEGATIVE_RESULT")
        state.advance_phase("phase1", "COMPLETED")
        assert state.phases[0].status == "COMPLETED"

    def test_invalid_transition_raises_valueerror(self):
        state = self._make_state_with_phase(initial_status="NOT_STARTED")
        with pytest.raises(ValueError, match="Invalid transition"):
            state.advance_phase("phase1", "COMPLETED")

    def test_invalid_transition_not_started_to_gate_check(self):
        state = self._make_state_with_phase(initial_status="NOT_STARTED")
        with pytest.raises(ValueError, match="Invalid transition"):
            state.advance_phase("phase1", "GATE_CHECK")

    def test_invalid_transition_completed_to_anything(self):
        state = self._make_state_with_phase(initial_status="COMPLETED")
        with pytest.raises(ValueError, match="Invalid transition"):
            state.advance_phase("phase1", "IN_PROGRESS")

    def test_unknown_phase_raises_valueerror(self):
        state = self._make_state_with_phase()
        with pytest.raises(ValueError, match="Phase .* not found"):
            state.advance_phase("nonexistent", "IN_PROGRESS")

    def test_advance_phase_updates_timestamp(self):
        state = self._make_state_with_phase()
        old_updated = state.updated_at
        state.advance_phase("phase1", "IN_PROGRESS")
        # updated_at should change (or at least not be before old)
        assert state.updated_at >= old_updated

    def test_gate_failed_increments_iteration_count(self):
        state = self._make_state_with_phase(initial_status="GATE_FAILED")
        state.advance_phase("phase1", "IN_PROGRESS")
        assert state.phases[0].iteration_count == 1


class TestGetCurrentPhase:
    """Tests for get_current_phase."""

    def test_returns_first_non_completed(self):
        state = ExperimentState(
            experiment_name="test",
            phases=[
                PhaseState(name="p1", status="COMPLETED"),
                PhaseState(name="p2", status="IN_PROGRESS"),
                PhaseState(name="p3", status="NOT_STARTED"),
            ],
        )
        result = state.get_current_phase()
        assert result is not None
        assert result.name == "p2"

    def test_returns_none_when_all_completed(self):
        state = ExperimentState(
            experiment_name="test",
            phases=[
                PhaseState(name="p1", status="COMPLETED"),
                PhaseState(name="p2", status="COMPLETED"),
            ],
        )
        result = state.get_current_phase()
        assert result is None

    def test_returns_first_phase_when_none_started(self):
        state = ExperimentState(
            experiment_name="test",
            phases=[
                PhaseState(name="p1", status="NOT_STARTED"),
                PhaseState(name="p2", status="NOT_STARTED"),
            ],
        )
        result = state.get_current_phase()
        assert result is not None
        assert result.name == "p1"

    def test_returns_none_for_empty_phases(self):
        state = ExperimentState(experiment_name="test", phases=[])
        result = state.get_current_phase()
        assert result is None


class TestPersistence:
    """Tests for save/load JSON persistence."""

    def test_save_creates_json_file(self, tmp_path):
        state = ExperimentState(
            experiment_name="test-exp",
            phases=[PhaseState(name="p1")],
        )
        filepath = tmp_path / "state.json"
        state.save(filepath)
        assert filepath.exists()

    def test_save_produces_valid_json(self, tmp_path):
        state = ExperimentState(
            experiment_name="test-exp",
            phases=[PhaseState(name="p1")],
        )
        filepath = tmp_path / "state.json"
        state.save(filepath)
        data = json.loads(filepath.read_text())
        assert data["experiment_name"] == "test-exp"
        assert len(data["phases"]) == 1

    def test_load_roundtrip(self, tmp_path):
        state = ExperimentState(
            experiment_name="roundtrip-exp",
            status="ACTIVE",
            phases=[
                PhaseState(name="p1", status="COMPLETED", iteration_count=2, metrics={"loss": 0.5}),
                PhaseState(name="p2", status="IN_PROGRESS"),
            ],
            current_phase="p2",
        )
        filepath = tmp_path / "state.json"
        state.save(filepath)
        loaded = ExperimentState.load(filepath)

        assert loaded.experiment_name == "roundtrip-exp"
        assert loaded.status == "ACTIVE"
        assert len(loaded.phases) == 2
        assert loaded.phases[0].name == "p1"
        assert loaded.phases[0].status == "COMPLETED"
        assert loaded.phases[0].iteration_count == 2
        assert loaded.phases[0].metrics["loss"] == 0.5
        assert loaded.phases[1].name == "p2"
        assert loaded.phases[1].status == "IN_PROGRESS"
        assert loaded.current_phase == "p2"
        assert loaded.created_at == state.created_at
        assert loaded.updated_at == state.updated_at

    def test_save_creates_parent_directories(self, tmp_path):
        state = ExperimentState(experiment_name="test")
        filepath = tmp_path / "nested" / "dir" / "state.json"
        state.save(filepath)
        assert filepath.exists()


class TestMetricsHistory:
    """PhaseState tracks metrics history across iterations."""

    def test_default_metrics_history_is_empty(self):
        phase = PhaseState(name="test_phase")
        assert phase.metrics_history == []

    def test_metrics_history_serializes(self, tmp_path):
        state = ExperimentState(
            experiment_name="test",
            phases=[PhaseState(
                name="phase1",
                metrics_history=[
                    {"iteration": 1, "timestamp": "2026-01-01T00:00:00Z", "metrics": {"acc": 0.5}, "gate_passed": False},
                    {"iteration": 2, "timestamp": "2026-01-02T00:00:00Z", "metrics": {"acc": 0.9}, "gate_passed": True},
                ],
            )],
        )
        path = tmp_path / "state.json"
        state.save(path)
        loaded = ExperimentState.load(path)
        assert len(loaded.phases[0].metrics_history) == 2
        assert loaded.phases[0].metrics_history[0]["metrics"]["acc"] == 0.5
        assert loaded.phases[0].metrics_history[1]["gate_passed"] is True

    def test_backward_compatible_load(self, tmp_path):
        """Loading old state.json without metrics_history works."""
        old_data = {
            "experiment_name": "old-exp",
            "status": "PLANNING",
            "phases": [
                {"name": "phase1", "status": "NOT_STARTED", "iteration_count": 0, "metrics": {}}
            ],
            "created_at": "2026-01-01T00:00:00Z",
            "updated_at": "2026-01-01T00:00:00Z",
            "current_phase": None,
        }
        path = tmp_path / "state.json"
        path.write_text(json.dumps(old_data))
        loaded = ExperimentState.load(path)
        assert loaded.phases[0].metrics_history == []
