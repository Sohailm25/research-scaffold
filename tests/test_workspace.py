# ABOUTME: Tests for scaffold/workspace.py - WorkspaceManager directory management and safety.
# ABOUTME: Covers workspace validation, path traversal prevention, result dirs, and artifact paths.

import pytest

from scaffold.workspace import WorkspaceManager


def _create_valid_workspace(base_path, name="test-experiment"):
    """Helper to create a minimal valid workspace structure."""
    exp_dir = base_path / name
    exp_dir.mkdir(parents=True)
    (exp_dir / "AGENTS.md").write_text("# Agents\n")
    (exp_dir / "configs").mkdir()
    (exp_dir / "configs" / "experiment.yaml").write_text("name: test\n")
    return exp_dir


class TestWorkspaceValidation:
    def test_validate_existing_workspace(self, tmp_path):
        _create_valid_workspace(tmp_path)
        ws = WorkspaceManager(root=tmp_path, experiment_name="test-experiment")
        ws.validate()  # should not raise

    def test_validate_missing_dir_raises(self, tmp_path):
        ws = WorkspaceManager(root=tmp_path, experiment_name="nonexistent")
        with pytest.raises(FileNotFoundError):
            ws.validate()

    def test_validate_missing_agents_md_raises(self, tmp_path):
        exp_dir = tmp_path / "test-experiment"
        exp_dir.mkdir()
        (exp_dir / "configs").mkdir()
        (exp_dir / "configs" / "experiment.yaml").write_text("name: test\n")
        # AGENTS.md is missing
        ws = WorkspaceManager(root=tmp_path, experiment_name="test-experiment")
        with pytest.raises(ValueError, match="AGENTS.md"):
            ws.validate()

    def test_validate_missing_config_raises(self, tmp_path):
        exp_dir = tmp_path / "test-experiment"
        exp_dir.mkdir()
        (exp_dir / "AGENTS.md").write_text("# Agents\n")
        (exp_dir / "configs").mkdir()
        # experiment.yaml is missing
        ws = WorkspaceManager(root=tmp_path, experiment_name="test-experiment")
        with pytest.raises(ValueError, match="experiment.yaml"):
            ws.validate()


class TestSafePath:
    def test_safe_path_normal(self, tmp_path):
        _create_valid_workspace(tmp_path)
        ws = WorkspaceManager(root=tmp_path, experiment_name="test-experiment")
        result = ws.safe_path("results/foo/bar.json")
        assert result == ws.experiment_dir / "results" / "foo" / "bar.json"

    def test_safe_path_traversal_raises(self, tmp_path):
        _create_valid_workspace(tmp_path)
        ws = WorkspaceManager(root=tmp_path, experiment_name="test-experiment")
        with pytest.raises(ValueError, match="escape"):
            ws.safe_path("../../../etc/passwd")

    def test_safe_path_absolute_raises(self, tmp_path):
        _create_valid_workspace(tmp_path)
        ws = WorkspaceManager(root=tmp_path, experiment_name="test-experiment")
        with pytest.raises(ValueError, match="escape"):
            ws.safe_path("/etc/passwd")

    def test_safe_path_dot_dot_in_middle(self, tmp_path):
        _create_valid_workspace(tmp_path)
        ws = WorkspaceManager(root=tmp_path, experiment_name="test-experiment")
        with pytest.raises(ValueError, match="escape"):
            ws.safe_path("results/../../../etc/passwd")


class TestResultDir:
    def test_result_dir_creates_directory(self, tmp_path):
        _create_valid_workspace(tmp_path)
        ws = WorkspaceManager(root=tmp_path, experiment_name="test-experiment")
        result = ws.result_dir("oracle-pilot")
        assert result.exists()
        assert result.is_dir()

    def test_result_dir_invalid_lane_raises(self, tmp_path):
        _create_valid_workspace(tmp_path)
        ws = WorkspaceManager(root=tmp_path, experiment_name="test-experiment")
        with pytest.raises(ValueError):
            ws.result_dir("bad/lane")
        with pytest.raises(ValueError):
            ws.result_dir("bad..lane")

    def test_result_dir_returns_correct_path(self, tmp_path):
        _create_valid_workspace(tmp_path)
        ws = WorkspaceManager(root=tmp_path, experiment_name="test-experiment")
        result = ws.result_dir("oracle-pilot")
        assert result == ws.experiment_dir / "results" / "oracle-pilot"


class TestArtifactPath:
    def test_artifact_path_in_lane(self, tmp_path):
        _create_valid_workspace(tmp_path)
        ws = WorkspaceManager(root=tmp_path, experiment_name="test-experiment")
        result = ws.artifact_path("oracle-pilot", "metrics.json")
        assert result == ws.experiment_dir / "results" / "oracle-pilot" / "metrics.json"

    def test_artifact_path_traversal_raises(self, tmp_path):
        _create_valid_workspace(tmp_path)
        ws = WorkspaceManager(root=tmp_path, experiment_name="test-experiment")
        with pytest.raises(ValueError):
            ws.artifact_path("oracle-pilot", "../../etc/passwd")


class TestSessionDir:
    def test_session_dir_path(self, tmp_path):
        _create_valid_workspace(tmp_path)
        ws = WorkspaceManager(root=tmp_path, experiment_name="test-experiment")
        result = ws.session_dir()
        assert result == ws.experiment_dir / "sessions"
