# ABOUTME: Tests for scaffold/init.py - experiment directory initialization from config.
# ABOUTME: Covers directory structure, template rendering, state persistence, and edge cases.

import json
from datetime import date
from pathlib import Path

import httpx
import pytest
import yaml

from scaffold.config import ExperimentConfig, load_config
from scaffold.init import init_experiment

FIXTURES_DIR = Path(__file__).parent / "fixtures"
MINIMAL_CONFIG = FIXTURES_DIR / "minimal_config.yaml"


@pytest.fixture
def config() -> ExperimentConfig:
    """Load the minimal test config."""
    return load_config(MINIMAL_CONFIG)


@pytest.fixture
def experiment_dir(tmp_path: Path, config: ExperimentConfig) -> Path:
    """Create an initialized experiment directory and return its path."""
    return init_experiment(config, root=tmp_path, skip_external=True)


# --- Directory Structure ---


class TestDirectoryStructure:
    """init_experiment creates all expected directories."""

    EXPECTED_DIRS = [
        "configs",
        "history",
        "sessions",
        "background-work",
        "background-work/source-docs",
        "background-work/papers",
        "scripts",
        "validation",
        "tests",
        "results",
        "results/infrastructure",
        "figures",
        "paper",
        "paper/figures",
        "paper/distill",
        "paper/distill/figures",
        "notebooks",
        "prompts",
        "research",
        "journal",
        "journal/logs",
        ".scaffold",
    ]

    def test_all_expected_directories_exist(self, experiment_dir: Path):
        for d in self.EXPECTED_DIRS:
            assert (experiment_dir / d).is_dir(), f"Missing directory: {d}"

    def test_lane_result_directories_exist(self, experiment_dir: Path, config: ExperimentConfig):
        for lane in config.required_lanes:
            lane_dir = experiment_dir / "results" / lane
            assert lane_dir.is_dir(), f"Missing lane directory: results/{lane}"

    def test_experiment_dir_name_matches_config(self, experiment_dir: Path, config: ExperimentConfig):
        assert experiment_dir.name == config.name

    def test_custom_name_override(self, tmp_path: Path, config: ExperimentConfig):
        result = init_experiment(config, root=tmp_path, name="custom-name", skip_external=True)
        assert result.name == "custom-name"
        assert result.is_dir()


# --- Rendered Files ---


class TestRenderedFiles:
    """All expected files exist after init."""

    EXPECTED_FILES = [
        ".gitignore",
        "README.md",
        "AGENTS.md",
        "WORKFLOW.md",
        "CURRENT_STATE.md",
        "DECISIONS.md",
        "SCRATCHPAD.md",
        "THOUGHT_LOG.md",
        "configs/experiment.yaml",
        "history/PREREG.md",
        "sessions/SESSION_TEMPLATE.md",
        "background-work/REFERENCES.md",
        "results/RESULTS_INDEX.md",
        "journal/current_state.md",
        ".scaffold/state.json",
        ".scaffold/artifacts.json",
    ]

    def test_all_expected_files_exist(self, experiment_dir: Path):
        for f in self.EXPECTED_FILES:
            assert (experiment_dir / f).is_file(), f"Missing file: {f}"

    def test_no_empty_rendered_files(self, experiment_dir: Path):
        """All rendered files should have non-empty content."""
        for f in self.EXPECTED_FILES:
            path = experiment_dir / f
            content = path.read_text()
            assert len(content.strip()) > 0, f"Empty file: {f}"


# --- AGENTS.md Content ---


class TestAgentsMdContent:
    """AGENTS.md contains key sections."""

    def test_has_epistemic_standards_section(self, experiment_dir: Path):
        content = (experiment_dir / "AGENTS.md").read_text()
        assert "## Epistemic Standards" in content

    def test_has_four_adversarial_questions(self, experiment_dir: Path):
        content = (experiment_dir / "AGENTS.md").read_text()
        assert "most likely design flaw" in content
        assert "simplest confound" in content
        assert "failure look like" in content
        assert "probability the implementation is wrong" in content

    def test_has_landing_the_plane_section(self, experiment_dir: Path):
        content = (experiment_dir / "AGENTS.md").read_text()
        assert "Landing the Plane" in content

    def test_has_beads_reference(self, experiment_dir: Path):
        content = (experiment_dir / "AGENTS.md").read_text()
        assert "bd" in content or "beads" in content

    def test_has_experiment_name(self, experiment_dir: Path, config: ExperimentConfig):
        content = (experiment_dir / "AGENTS.md").read_text()
        assert config.name in content

    def test_has_framing_locks(self, experiment_dir: Path, config: ExperimentConfig):
        content = (experiment_dir / "AGENTS.md").read_text()
        for lock in config.framing_locks:
            assert lock in content

    def test_has_required_lanes(self, experiment_dir: Path, config: ExperimentConfig):
        content = (experiment_dir / "AGENTS.md").read_text()
        for lane in config.required_lanes:
            assert lane in content


# --- CURRENT_STATE.md Content ---


class TestCurrentStateMdContent:
    """CURRENT_STATE.md has phase status, models, runtime."""

    def test_has_phase_status_table(self, experiment_dir: Path):
        content = (experiment_dir / "CURRENT_STATE.md").read_text()
        assert "Phase" in content
        assert "Status" in content

    def test_has_all_phases(self, experiment_dir: Path, config: ExperimentConfig):
        content = (experiment_dir / "CURRENT_STATE.md").read_text()
        for phase in config.phases:
            assert phase.name in content

    def test_has_model_info(self, experiment_dir: Path, config: ExperimentConfig):
        content = (experiment_dir / "CURRENT_STATE.md").read_text()
        assert config.models.development.name in content
        assert config.models.primary.name in content

    def test_has_runtime_info(self, experiment_dir: Path, config: ExperimentConfig):
        content = (experiment_dir / "CURRENT_STATE.md").read_text()
        assert config.runtime.accelerator in content

    def test_has_required_lanes(self, experiment_dir: Path, config: ExperimentConfig):
        content = (experiment_dir / "CURRENT_STATE.md").read_text()
        for lane in config.required_lanes:
            assert lane in content


# --- PREREG.md Content ---


class TestPreregContent:
    """PREREG.md has hypotheses, null models, gates."""

    def test_has_primary_hypothesis(self, experiment_dir: Path, config: ExperimentConfig):
        content = (experiment_dir / "history" / "PREREG.md").read_text()
        assert config.hypotheses.primary in content

    def test_has_secondary_hypotheses(self, experiment_dir: Path, config: ExperimentConfig):
        content = (experiment_dir / "history" / "PREREG.md").read_text()
        for h in config.hypotheses.secondary:
            assert h in content

    def test_has_null_models(self, experiment_dir: Path, config: ExperimentConfig):
        content = (experiment_dir / "history" / "PREREG.md").read_text()
        for nm in config.null_models:
            assert nm.name in content

    def test_has_phase_gates(self, experiment_dir: Path, config: ExperimentConfig):
        content = (experiment_dir / "history" / "PREREG.md").read_text()
        for phase in config.phases:
            assert phase.name in content
            for gate in phase.gates:
                assert gate.metric in content

    def test_has_statistics(self, experiment_dir: Path, config: ExperimentConfig):
        content = (experiment_dir / "history" / "PREREG.md").read_text()
        for key in config.statistics:
            assert key in content


# --- experiment.yaml Content ---


class TestExperimentYamlContent:
    """Rendered experiment.yaml is valid YAML matching source config."""

    def test_is_valid_yaml(self, experiment_dir: Path):
        path = experiment_dir / "configs" / "experiment.yaml"
        data = yaml.safe_load(path.read_text())
        assert data is not None

    def test_has_experiment_name(self, experiment_dir: Path, config: ExperimentConfig):
        path = experiment_dir / "configs" / "experiment.yaml"
        data = yaml.safe_load(path.read_text())
        assert data["experiment"]["name"] == config.name

    def test_has_thesis(self, experiment_dir: Path, config: ExperimentConfig):
        path = experiment_dir / "configs" / "experiment.yaml"
        data = yaml.safe_load(path.read_text())
        assert data["experiment"]["thesis"] == config.thesis

    def test_has_required_lanes(self, experiment_dir: Path, config: ExperimentConfig):
        path = experiment_dir / "configs" / "experiment.yaml"
        data = yaml.safe_load(path.read_text())
        assert data["required_lanes"] == config.required_lanes

    def test_has_models(self, experiment_dir: Path, config: ExperimentConfig):
        path = experiment_dir / "configs" / "experiment.yaml"
        data = yaml.safe_load(path.read_text())
        assert data["models"]["development"]["name"] == config.models.development.name
        assert data["models"]["primary"]["name"] == config.models.primary.name

    def test_has_phases(self, experiment_dir: Path, config: ExperimentConfig):
        path = experiment_dir / "configs" / "experiment.yaml"
        data = yaml.safe_load(path.read_text())
        assert len(data["phases"]) == len(config.phases)
        assert data["phases"][0]["name"] == config.phases[0].name


# --- WORKFLOW.md Content ---


class TestWorkflowMdContent:
    """WORKFLOW.md has YAML frontmatter and raw Jinja2 variables preserved."""

    def test_has_yaml_frontmatter(self, experiment_dir: Path):
        content = (experiment_dir / "WORKFLOW.md").read_text()
        assert content.startswith("---")
        # Second --- closes the frontmatter
        parts = content.split("---", 2)
        assert len(parts) >= 3, "WORKFLOW.md should have YAML frontmatter delimiters"

    def test_frontmatter_has_runtime(self, experiment_dir: Path, config: ExperimentConfig):
        content = (experiment_dir / "WORKFLOW.md").read_text()
        parts = content.split("---", 2)
        frontmatter = yaml.safe_load(parts[1])
        assert frontmatter["runtime"]["accelerator"] == config.runtime.accelerator

    def test_has_raw_jinja_variables(self, experiment_dir: Path):
        """WORKFLOW.md preserves {{ phase }}, {{ lane }}, {{ task }} as raw Jinja2."""
        content = (experiment_dir / "WORKFLOW.md").read_text()
        assert "{{ phase }}" in content
        assert "{{ lane }}" in content
        assert "{{ task }}" in content

    def test_has_experiment_name(self, experiment_dir: Path, config: ExperimentConfig):
        content = (experiment_dir / "WORKFLOW.md").read_text()
        assert config.name in content


# --- State Persistence ---


class TestStatePersistence:
    """.scaffold/state.json exists and is valid."""

    def test_state_json_exists(self, experiment_dir: Path):
        assert (experiment_dir / ".scaffold" / "state.json").is_file()

    def test_state_json_is_valid(self, experiment_dir: Path):
        path = experiment_dir / ".scaffold" / "state.json"
        data = json.loads(path.read_text())
        assert "experiment_name" in data
        assert "status" in data
        assert "phases" in data

    def test_state_has_correct_experiment_name(self, experiment_dir: Path, config: ExperimentConfig):
        path = experiment_dir / ".scaffold" / "state.json"
        data = json.loads(path.read_text())
        assert data["experiment_name"] == config.name

    def test_state_phases_match_config(self, experiment_dir: Path, config: ExperimentConfig):
        path = experiment_dir / ".scaffold" / "state.json"
        data = json.loads(path.read_text())
        phase_names = [p["name"] for p in data["phases"]]
        config_phase_names = [p.name for p in config.phases]
        assert phase_names == config_phase_names

    def test_state_status_is_planning(self, experiment_dir: Path):
        path = experiment_dir / ".scaffold" / "state.json"
        data = json.loads(path.read_text())
        assert data["status"] == "PLANNING"


# --- Artifacts Persistence ---


class TestArtifactsPersistence:
    """.scaffold/artifacts.json exists and is valid."""

    def test_artifacts_json_exists(self, experiment_dir: Path):
        assert (experiment_dir / ".scaffold" / "artifacts.json").is_file()

    def test_artifacts_json_is_valid(self, experiment_dir: Path):
        path = experiment_dir / ".scaffold" / "artifacts.json"
        data = json.loads(path.read_text())
        assert isinstance(data, list)

    def test_artifacts_starts_empty(self, experiment_dir: Path):
        path = experiment_dir / ".scaffold" / "artifacts.json"
        data = json.loads(path.read_text())
        assert len(data) == 0


# --- RESULTS_INDEX.md Content ---


class TestResultsIndexContent:
    """RESULTS_INDEX.md has one table per lane."""

    def test_has_infrastructure_table(self, experiment_dir: Path):
        content = (experiment_dir / "results" / "RESULTS_INDEX.md").read_text()
        assert "## Infrastructure" in content

    def test_has_lane_tables(self, experiment_dir: Path, config: ExperimentConfig):
        content = (experiment_dir / "results" / "RESULTS_INDEX.md").read_text()
        for lane in config.required_lanes:
            heading = lane.replace("_", " ").title()
            assert f"## {heading}" in content

    def test_has_figures_table(self, experiment_dir: Path):
        content = (experiment_dir / "results" / "RESULTS_INDEX.md").read_text()
        assert "## Figures" in content

    def test_has_table_headers(self, experiment_dir: Path):
        content = (experiment_dir / "results" / "RESULTS_INDEX.md").read_text()
        assert "| Artifact | Lane | Status | Path |" in content


# --- Init From YAML Path ---


class TestInitFromYamlPath:
    """Can init from a YAML file path instead of ExperimentConfig object."""

    def test_init_from_path(self, tmp_path: Path):
        result = init_experiment(MINIMAL_CONFIG, root=tmp_path, skip_external=True)
        assert result.is_dir()
        assert (result / "AGENTS.md").is_file()

    def test_init_from_path_uses_config_name(self, tmp_path: Path):
        result = init_experiment(MINIMAL_CONFIG, root=tmp_path, skip_external=True)
        assert result.name == "test-experiment"

    def test_init_from_path_with_name_override(self, tmp_path: Path):
        result = init_experiment(MINIMAL_CONFIG, root=tmp_path, name="override-name", skip_external=True)
        assert result.name == "override-name"


# --- Init Idempotency ---


class TestInitIdempotency:
    """Calling init twice on same path raises error."""

    def test_second_init_raises(self, tmp_path: Path, config: ExperimentConfig):
        init_experiment(config, root=tmp_path, skip_external=True)
        with pytest.raises(FileExistsError):
            init_experiment(config, root=tmp_path, skip_external=True)

    def test_different_names_do_not_conflict(self, tmp_path: Path, config: ExperimentConfig):
        init_experiment(config, root=tmp_path, name="exp-a", skip_external=True)
        result = init_experiment(config, root=tmp_path, name="exp-b", skip_external=True)
        assert result.name == "exp-b"
        assert result.is_dir()


# --- journal/current_state.md Content ---


class TestJournalCurrentState:
    """journal/current_state.md is created directly with expected content."""

    def test_has_date(self, experiment_dir: Path):
        content = (experiment_dir / "journal" / "current_state.md").read_text()
        today = date.today().isoformat()
        assert today in content

    def test_has_scaffold_status(self, experiment_dir: Path):
        content = (experiment_dir / "journal" / "current_state.md").read_text()
        assert "scaffold initialized" in content

    def test_has_branch_reference(self, experiment_dir: Path, config: ExperimentConfig):
        content = (experiment_dir / "journal" / "current_state.md").read_text()
        assert f"wip/{config.name}-scaffold" in content

    def test_has_phase_0(self, experiment_dir: Path):
        content = (experiment_dir / "journal" / "current_state.md").read_text()
        assert "Phase 0" in content


# --- background-work/REFERENCES.md Content ---


class TestReferencesContent:
    """background-work/REFERENCES.md is created directly with expected content."""

    def test_has_papers_table(self, experiment_dir: Path):
        content = (experiment_dir / "background-work" / "REFERENCES.md").read_text()
        assert "## Papers" in content
        assert "| Paper |" in content

    def test_has_tools_table(self, experiment_dir: Path):
        content = (experiment_dir / "background-work" / "REFERENCES.md").read_text()
        assert "## Tools and Libraries" in content
        assert "| Tool |" in content

    def test_has_urls_section(self, experiment_dir: Path):
        content = (experiment_dir / "background-work" / "REFERENCES.md").read_text()
        assert "## URLs" in content


# --- Linear Integration ---


class _FakeTransport(httpx.BaseTransport):
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


class TestLinearIntegration:
    """init_experiment creates a Linear issue when skip_external=False."""

    def test_init_creates_linear_issue(self, tmp_path: Path, config: ExperimentConfig):
        """Linear issue is created and issue_id saved to .scaffold/linear.json."""
        canned_list = {
            "data": {
                "project": {
                    "issues": {"nodes": []}
                }
            }
        }
        canned_create = {
            "data": {
                "issueCreate": {
                    "success": True,
                    "issue": {"id": "issue-init-test-123"},
                }
            }
        }
        transport = _FakeTransport(responses=[canned_list, canned_create])
        http_client = httpx.Client(transport=transport)

        from scaffold.linear import LinearClient

        result = init_experiment(
            config, root=tmp_path, skip_external=False,
            _linear_client=LinearClient(api_key="test-key", client=http_client),
        )

        linear_json = result / ".scaffold" / "linear.json"
        assert linear_json.is_file()
        data = json.loads(linear_json.read_text())
        assert data["issue_id"] == "issue-init-test-123"

        # Verify requests: first list_experiments, then create
        assert len(transport.requests) == 2
        body = json.loads(transport.requests[1].content)
        assert body["variables"]["input"]["title"] == config.name
        assert body["variables"]["input"]["description"] == config.research_question

    def test_init_linear_failure_graceful(self, tmp_path: Path, config: ExperimentConfig):
        """Linear failure does not prevent experiment initialization."""
        # Transport that returns an error
        transport = _FakeTransport(responses=[{"errors": [{"message": "Auth failed"}]}])
        http_client = httpx.Client(transport=transport)

        from scaffold.linear import LinearClient

        result = init_experiment(
            config, root=tmp_path, skip_external=False,
            _linear_client=LinearClient(api_key="bad-key", client=http_client),
        )

        # Experiment dir should still exist and be valid
        assert result.is_dir()
        assert (result / "AGENTS.md").is_file()
        assert (result / ".scaffold" / "state.json").is_file()

        # linear.json should NOT exist since it failed
        linear_json = result / ".scaffold" / "linear.json"
        assert not linear_json.exists()

    def test_init_skips_linear_when_skip_external(self, tmp_path: Path, config: ExperimentConfig):
        """skip_external=True skips Linear issue creation (no linear.json)."""
        result = init_experiment(config, root=tmp_path, skip_external=True)

        linear_json = result / ".scaffold" / "linear.json"
        assert not linear_json.exists()


# --- Git Init ---


class TestGitInit:
    """init_experiment runs git init when skip_external=False."""

    def test_init_runs_git_init(self, tmp_path: Path, config: ExperimentConfig):
        """When skip_external=False, experiment dir should have .git/ directory."""
        exp_dir = init_experiment(config, root=tmp_path, skip_external=False)
        assert (exp_dir / ".git").is_dir(), "Expected .git directory when skip_external=False"

    def test_init_has_initial_commit(self, tmp_path: Path, config: ExperimentConfig):
        """When skip_external=False, the repo should have exactly one commit."""
        import subprocess

        exp_dir = init_experiment(config, root=tmp_path, skip_external=False)
        result = subprocess.run(
            ["git", "log", "--oneline"],
            cwd=exp_dir,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        lines = result.stdout.strip().splitlines()
        assert len(lines) == 1
        assert "Initialize experiment" in lines[0]

    def test_init_no_git_when_skip_external(self, tmp_path: Path, config: ExperimentConfig):
        """When skip_external=True, no .git directory should be created."""
        exp_dir = init_experiment(config, root=tmp_path, skip_external=True)
        assert not (exp_dir / ".git").exists(), "Expected no .git directory when skip_external=True"
