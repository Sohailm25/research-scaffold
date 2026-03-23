# ABOUTME: Tests for scaffold/linear.py - Linear GraphQL adapter for experiment tracking.
# ABOUTME: Uses _FakeTransport to record requests and return canned responses.

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
import yaml

from scaffold.linear import (
    DEFAULT_PROJECT_ID,
    DEFAULT_TEAM_ID,
    LINEAR_API_URL,
    STATE_IDS,
    LinearAPIError,
    LinearClient,
    load_scaffold_config,
)


class _FakeTransport(httpx.BaseTransport):
    """Records requests and returns canned responses."""

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


def _make_client(responses=None, api_key="test-key-123"):
    """Helper to build a LinearClient with a fake transport."""
    transport = _FakeTransport(responses=responses)
    http_client = httpx.Client(transport=transport)
    client = LinearClient(api_key=api_key, client=http_client)
    return client, transport


# --- load_scaffold_config ---


class TestLoadScaffoldConfig:
    def test_loads_yaml_file(self, tmp_path, monkeypatch):
        config_dir = tmp_path / ".scaffold"
        config_dir.mkdir()
        config_file = config_dir / "config.yaml"
        config_file.write_text(yaml.dump({"linear_api_key": "sk-test", "other": 42}))
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        result = load_scaffold_config()
        assert result["linear_api_key"] == "sk-test"
        assert result["other"] == 42

    def test_raises_when_missing(self, tmp_path, monkeypatch):
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        with pytest.raises(FileNotFoundError, match="config"):
            load_scaffold_config()

    def test_empty_yaml_returns_empty_dict(self, tmp_path, monkeypatch):
        config_dir = tmp_path / ".scaffold"
        config_dir.mkdir()
        config_file = config_dir / "config.yaml"
        config_file.write_text("")
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        result = load_scaffold_config()
        assert result == {}


# --- LinearClient.__init__ ---


class TestLinearClientInit:
    def test_init_with_explicit_api_key(self):
        transport = _FakeTransport()
        http_client = httpx.Client(transport=transport)
        client = LinearClient(api_key="my-key", client=http_client)
        assert client._api_key == "my-key"
        assert client._team_id == DEFAULT_TEAM_ID
        assert client._project_id == DEFAULT_PROJECT_ID

    def test_init_loads_key_from_config(self, tmp_path, monkeypatch):
        config_dir = tmp_path / ".scaffold"
        config_dir.mkdir()
        config_file = config_dir / "config.yaml"
        config_file.write_text(yaml.dump({"linear_api_key": "sk-from-config"}))
        monkeypatch.setattr(Path, "home", lambda: tmp_path)

        transport = _FakeTransport()
        http_client = httpx.Client(transport=transport)
        client = LinearClient(client=http_client)
        assert client._api_key == "sk-from-config"

    def test_init_raises_when_no_key_anywhere(self, tmp_path, monkeypatch):
        config_dir = tmp_path / ".scaffold"
        config_dir.mkdir()
        config_file = config_dir / "config.yaml"
        config_file.write_text(yaml.dump({"other_key": "value"}))
        monkeypatch.setattr(Path, "home", lambda: tmp_path)

        with pytest.raises(ValueError, match="API key"):
            LinearClient()

    def test_init_custom_team_and_project(self):
        transport = _FakeTransport()
        http_client = httpx.Client(transport=transport)
        client = LinearClient(
            api_key="key",
            team_id="custom-team",
            project_id="custom-project",
            client=http_client,
        )
        assert client._team_id == "custom-team"
        assert client._project_id == "custom-project"


# --- create_experiment_issue ---


class TestCreateExperimentIssue:
    def test_sends_issue_create_mutation(self):
        canned = {
            "data": {
                "issueCreate": {
                    "success": True,
                    "issue": {"id": "issue-abc-123"},
                }
            }
        }
        client, transport = _make_client(responses=[canned])
        issue_id = client.create_experiment_issue("My Experiment", "Description here")

        assert issue_id == "issue-abc-123"
        assert len(transport.requests) == 1

        # Verify the request payload
        req = transport.requests[0]
        body = json.loads(req.content)
        assert "issueCreate" in body["query"]
        variables = body["variables"]
        assert variables["input"]["title"] == "My Experiment"
        assert variables["input"]["description"] == "Description here"
        assert variables["input"]["teamId"] == DEFAULT_TEAM_ID
        assert variables["input"]["projectId"] == DEFAULT_PROJECT_ID
        assert variables["input"]["stateId"] == STATE_IDS["Todo"]

    def test_sends_to_correct_url(self):
        canned = {
            "data": {
                "issueCreate": {
                    "success": True,
                    "issue": {"id": "issue-xyz"},
                }
            }
        }
        client, transport = _make_client(responses=[canned])
        client.create_experiment_issue("Title", "Desc")

        req = transport.requests[0]
        assert str(req.url) == LINEAR_API_URL

    def test_sends_auth_header(self):
        canned = {
            "data": {
                "issueCreate": {
                    "success": True,
                    "issue": {"id": "issue-xyz"},
                }
            }
        }
        client, transport = _make_client(responses=[canned], api_key="bearer-token-123")
        client.create_experiment_issue("Title", "Desc")

        req = transport.requests[0]
        assert req.headers["authorization"] == "bearer-token-123"

    def test_raises_on_unsuccessful_create(self):
        canned = {
            "data": {
                "issueCreate": {
                    "success": False,
                    "issue": None,
                }
            }
        }
        client, transport = _make_client(responses=[canned])
        with pytest.raises(LinearAPIError, match="create issue"):
            client.create_experiment_issue("Title", "Desc")


# --- update_experiment_status ---


class TestUpdateExperimentStatus:
    def test_sends_issue_update_with_state_id(self):
        canned = {"data": {"issueUpdate": {"success": True}}}
        client, transport = _make_client(responses=[canned])
        client.update_experiment_status("issue-42", "In Progress")

        assert len(transport.requests) == 1
        body = json.loads(transport.requests[0].content)
        assert "issueUpdate" in body["query"]
        assert body["variables"]["id"] == "issue-42"
        assert body["variables"]["input"]["stateId"] == STATE_IDS["In Progress"]

    def test_all_valid_state_names(self):
        for state_name, state_id in STATE_IDS.items():
            canned = {"data": {"issueUpdate": {"success": True}}}
            client, transport = _make_client(responses=[canned])
            client.update_experiment_status("issue-1", state_name)

            body = json.loads(transport.requests[0].content)
            assert body["variables"]["input"]["stateId"] == state_id

    def test_raises_on_unknown_state(self):
        client, _ = _make_client()
        with pytest.raises(ValueError, match="Unknown state"):
            client.update_experiment_status("issue-1", "Nonexistent")

    def test_raises_on_unsuccessful_update(self):
        canned = {"data": {"issueUpdate": {"success": False}}}
        client, transport = _make_client(responses=[canned])
        with pytest.raises(LinearAPIError, match="update issue"):
            client.update_experiment_status("issue-1", "Done")


# --- add_phase_comment ---


class TestAddPhaseComment:
    def test_sends_comment_create_mutation(self):
        canned = {"data": {"commentCreate": {"success": True}}}
        client, transport = _make_client(responses=[canned])

        gate_report = {
            "overall_pass": True,
            "results": [
                {
                    "metric": "accuracy",
                    "status": "PASS",
                    "observed_value": 0.95,
                    "threshold": 0.90,
                    "comparator": "gte",
                },
                {
                    "metric": "latency",
                    "status": "PASS",
                    "observed_value": 120,
                    "threshold": 200,
                    "comparator": "lte",
                },
            ],
        }
        client.add_phase_comment("issue-42", "phase1_oracle", gate_report)

        assert len(transport.requests) == 1
        body = json.loads(transport.requests[0].content)
        assert "commentCreate" in body["query"]
        assert body["variables"]["input"]["issueId"] == "issue-42"

        comment_body = body["variables"]["input"]["body"]
        assert "phase1_oracle" in comment_body
        assert "PASS" in comment_body
        assert "accuracy" in comment_body
        assert "0.95" in comment_body

    def test_comment_body_includes_fail(self):
        canned = {"data": {"commentCreate": {"success": True}}}
        client, transport = _make_client(responses=[canned])

        gate_report = {
            "overall_pass": False,
            "results": [
                {
                    "metric": "r_squared",
                    "status": "FAIL",
                    "observed_value": 0.3,
                    "threshold": 0.5,
                    "comparator": "gte",
                },
            ],
        }
        client.add_phase_comment("issue-99", "phase2_routing", gate_report)

        body = json.loads(transport.requests[0].content)
        comment_body = body["variables"]["input"]["body"]
        assert "FAIL" in comment_body
        assert "r_squared" in comment_body

    def test_raises_on_unsuccessful_comment(self):
        canned = {"data": {"commentCreate": {"success": False}}}
        client, transport = _make_client(responses=[canned])
        with pytest.raises(LinearAPIError, match="comment"):
            client.add_phase_comment("issue-1", "phase1", {"overall_pass": True, "results": []})

    def test_comment_includes_table_with_thresholds(self):
        """Comment body contains a markdown table with Threshold column."""
        canned = {"data": {"commentCreate": {"success": True}}}
        client, transport = _make_client(responses=[canned])

        gate_report = {
            "overall_pass": True,
            "results": [
                {
                    "metric": "pca_variance",
                    "status": "PASS",
                    "observed_value": 0.4767,
                    "threshold": 0.40,
                    "comparator": "gte",
                },
            ],
        }
        client.add_phase_comment("issue-1", "pilot_single_model", gate_report)

        body = json.loads(transport.requests[0].content)
        comment_body = body["variables"]["input"]["body"]
        # Table header
        assert "| Gate |" in comment_body
        assert "Threshold" in comment_body
        assert "Observed" in comment_body
        assert "Status" in comment_body
        # Table row
        assert "pca_variance" in comment_body
        assert ">= 0.4" in comment_body
        assert "0.4767" in comment_body

    def test_pass_comment_format(self):
        """PASS comments say 'PASSED' and include the table."""
        canned = {"data": {"commentCreate": {"success": True}}}
        client, transport = _make_client(responses=[canned])

        gate_report = {
            "overall_pass": True,
            "results": [
                {
                    "metric": "accuracy",
                    "status": "PASS",
                    "observed_value": 0.96,
                    "threshold": 0.65,
                    "comparator": "gte",
                },
                {
                    "metric": "auroc",
                    "status": "PASS",
                    "observed_value": 0.80,
                    "threshold": 0.70,
                    "comparator": "gte",
                },
                {
                    "metric": "loss",
                    "status": "PASS",
                    "observed_value": 0.01,
                    "threshold": 0.05,
                    "comparator": "lte",
                },
            ],
        }
        client.add_phase_comment(
            "issue-1", "pilot_single_model", gate_report, iteration=1
        )

        body = json.loads(transport.requests[0].content)
        comment_body = body["variables"]["input"]["body"]
        assert "PASSED" in comment_body
        assert "All 3 gates passed" in comment_body
        assert "| Gate |" in comment_body
        assert "*Status: Awaiting human review before advancing.*" in comment_body

    def test_fail_comment_shows_failure_count(self):
        """FAIL comments show 'X of Y gates failed'."""
        canned = {"data": {"commentCreate": {"success": True}}}
        client, transport = _make_client(responses=[canned])

        gate_report = {
            "overall_pass": False,
            "results": [
                {
                    "metric": "accuracy",
                    "status": "PASS",
                    "observed_value": 0.96,
                    "threshold": 0.65,
                    "comparator": "gte",
                },
                {
                    "metric": "auroc",
                    "status": "FAIL",
                    "observed_value": 0.43,
                    "threshold": 0.70,
                    "comparator": "gte",
                },
                {
                    "metric": "f1",
                    "status": "FAIL",
                    "observed_value": 0.30,
                    "threshold": 0.50,
                    "comparator": "gte",
                },
            ],
        }
        client.add_phase_comment(
            "issue-1", "failure_prediction_validation", gate_report,
            iteration=2, max_iterations=20,
        )

        body = json.loads(transport.requests[0].content)
        comment_body = body["variables"]["input"]["body"]
        assert "**Result: FAIL**" in comment_body
        assert "2 of 3 gates failed" in comment_body
        assert "Orchestrator will retry" in comment_body

    def test_all_skip_comment_format(self):
        """All-SKIP results show 'NO METRICS' text."""
        canned = {"data": {"commentCreate": {"success": True}}}
        client, transport = _make_client(responses=[canned])

        gate_report = {
            "overall_pass": False,
            "results": [
                {
                    "metric": "accuracy",
                    "status": "SKIP",
                    "observed_value": None,
                    "threshold": 0.65,
                    "comparator": "gte",
                },
                {
                    "metric": "auroc",
                    "status": "SKIP",
                    "observed_value": None,
                    "threshold": 0.70,
                    "comparator": "gte",
                },
                {
                    "metric": "f1",
                    "status": "SKIP",
                    "observed_value": None,
                    "threshold": 0.50,
                    "comparator": "gte",
                },
            ],
        }
        client.add_phase_comment(
            "issue-1", "failure_prediction_validation", gate_report,
            iteration=3, max_iterations=20,
        )

        body = json.loads(transport.requests[0].content)
        comment_body = body["variables"]["input"]["body"]
        assert "**Result: NO METRICS**" in comment_body
        assert "All 3 gates evaluated as SKIP" in comment_body
        assert "agent did not produce any metrics" in comment_body

    def test_comment_includes_iteration(self):
        """Iteration context appears as 'Iteration 2/20'."""
        canned = {"data": {"commentCreate": {"success": True}}}
        client, transport = _make_client(responses=[canned])

        gate_report = {
            "overall_pass": False,
            "results": [
                {
                    "metric": "accuracy",
                    "status": "FAIL",
                    "observed_value": 0.50,
                    "threshold": 0.65,
                    "comparator": "gte",
                },
            ],
        }
        client.add_phase_comment(
            "issue-1", "phase1", gate_report,
            iteration=2, max_iterations=20,
        )

        body = json.loads(transport.requests[0].content)
        comment_body = body["variables"]["input"]["body"]
        assert "Iteration 2/20" in comment_body

    def test_comment_without_iteration(self):
        """When iteration is None, no iteration text appears."""
        canned = {"data": {"commentCreate": {"success": True}}}
        client, transport = _make_client(responses=[canned])

        gate_report = {
            "overall_pass": True,
            "results": [
                {
                    "metric": "accuracy",
                    "status": "PASS",
                    "observed_value": 0.96,
                    "threshold": 0.65,
                    "comparator": "gte",
                },
            ],
        }
        client.add_phase_comment("issue-1", "phase1", gate_report)

        body = json.loads(transport.requests[0].content)
        comment_body = body["variables"]["input"]["body"]
        assert "Iteration" not in comment_body

    def test_comparator_display(self):
        """Comparator codes are displayed as symbols: gte->'>=', lte->'<=', etc."""
        canned = {"data": {"commentCreate": {"success": True}}}
        client, transport = _make_client(responses=[canned])

        gate_report = {
            "overall_pass": True,
            "results": [
                {
                    "metric": "metric_a",
                    "status": "PASS",
                    "observed_value": 1.0,
                    "threshold": 0.5,
                    "comparator": "gte",
                },
                {
                    "metric": "metric_b",
                    "status": "PASS",
                    "observed_value": 0.1,
                    "threshold": 0.5,
                    "comparator": "lte",
                },
                {
                    "metric": "metric_c",
                    "status": "PASS",
                    "observed_value": 1.0,
                    "threshold": 0.5,
                    "comparator": "gt",
                },
                {
                    "metric": "metric_d",
                    "status": "PASS",
                    "observed_value": 0.1,
                    "threshold": 0.5,
                    "comparator": "lt",
                },
                {
                    "metric": "metric_e",
                    "status": "PASS",
                    "observed_value": 0.5,
                    "threshold": 0.5,
                    "comparator": "eq",
                },
            ],
        }
        client.add_phase_comment("issue-1", "phase1", gate_report)

        body = json.loads(transport.requests[0].content)
        comment_body = body["variables"]["input"]["body"]
        assert ">= 0.5" in comment_body
        assert "<= 0.5" in comment_body
        assert "> 0.5" in comment_body
        assert "< 0.5" in comment_body
        assert "= 0.5" in comment_body


# --- list_experiments ---


class TestListExperiments:
    def test_returns_list_of_dicts(self):
        canned = {
            "data": {
                "project": {
                    "issues": {
                        "nodes": [
                            {
                                "id": "issue-1",
                                "title": "Experiment Alpha",
                                "description": "Test alpha",
                                "state": {"name": "In Progress", "type": "started"},
                                "createdAt": "2026-01-01T00:00:00Z",
                                "updatedAt": "2026-01-02T00:00:00Z",
                            },
                            {
                                "id": "issue-2",
                                "title": "Experiment Beta",
                                "description": "Test beta",
                                "state": {"name": "Done", "type": "completed"},
                                "createdAt": "2026-02-01T00:00:00Z",
                                "updatedAt": "2026-02-05T00:00:00Z",
                            },
                        ]
                    }
                }
            }
        }
        client, transport = _make_client(responses=[canned])
        experiments = client.list_experiments()

        assert len(experiments) == 2
        assert experiments[0]["id"] == "issue-1"
        assert experiments[0]["title"] == "Experiment Alpha"
        assert experiments[0]["state"] == "In Progress"
        assert experiments[0]["created_at"] == "2026-01-01T00:00:00Z"
        assert experiments[1]["id"] == "issue-2"
        assert experiments[1]["title"] == "Experiment Beta"
        assert experiments[1]["state"] == "Done"

    def test_sends_project_id_in_query(self):
        canned = {
            "data": {
                "project": {
                    "issues": {"nodes": []}
                }
            }
        }
        client, transport = _make_client(responses=[canned])
        client.list_experiments()

        body = json.loads(transport.requests[0].content)
        assert body["variables"]["projectId"] == DEFAULT_PROJECT_ID

    def test_empty_project_returns_empty_list(self):
        canned = {
            "data": {
                "project": {
                    "issues": {"nodes": []}
                }
            }
        }
        client, transport = _make_client(responses=[canned])
        experiments = client.list_experiments()
        assert experiments == []

    def test_handles_missing_optional_fields(self):
        canned = {
            "data": {
                "project": {
                    "issues": {
                        "nodes": [
                            {
                                "id": "issue-3",
                                "title": "Sparse Issue",
                                "state": {"name": "Todo", "type": "unstarted"},
                                "createdAt": "2026-03-01T00:00:00Z",
                                "updatedAt": "2026-03-01T00:00:00Z",
                            },
                        ]
                    }
                }
            }
        }
        client, transport = _make_client(responses=[canned])
        experiments = client.list_experiments()
        assert experiments[0]["description"] == ""


# --- find_experiment_issue ---


class TestFindExperimentIssue:
    def test_find_experiment_issue_returns_id(self):
        """Returns the issue ID when an issue with matching title exists."""
        canned = {
            "data": {
                "project": {
                    "issues": {
                        "nodes": [
                            {
                                "id": "issue-1",
                                "title": "Experiment Alpha",
                                "description": "Test alpha",
                                "state": {"name": "In Progress", "type": "started"},
                                "createdAt": "2026-01-01T00:00:00Z",
                                "updatedAt": "2026-01-02T00:00:00Z",
                            },
                            {
                                "id": "issue-2",
                                "title": "Experiment Beta",
                                "description": "Test beta",
                                "state": {"name": "Done", "type": "completed"},
                                "createdAt": "2026-02-01T00:00:00Z",
                                "updatedAt": "2026-02-05T00:00:00Z",
                            },
                        ]
                    }
                }
            }
        }
        client, transport = _make_client(responses=[canned])
        result = client.find_experiment_issue("Experiment Beta")
        assert result == "issue-2"

    def test_find_experiment_issue_returns_none(self):
        """Returns None when no issue has the matching title."""
        canned = {
            "data": {
                "project": {
                    "issues": {
                        "nodes": [
                            {
                                "id": "issue-1",
                                "title": "Experiment Alpha",
                                "description": "Test alpha",
                                "state": {"name": "In Progress", "type": "started"},
                                "createdAt": "2026-01-01T00:00:00Z",
                                "updatedAt": "2026-01-02T00:00:00Z",
                            },
                        ]
                    }
                }
            }
        }
        client, transport = _make_client(responses=[canned])
        result = client.find_experiment_issue("Nonexistent Experiment")
        assert result is None


# --- Error handling ---


class TestErrorHandling:
    def test_api_errors_raise_linear_api_error(self):
        canned = {
            "errors": [
                {"message": "Authentication failed"},
            ]
        }
        client, transport = _make_client(responses=[canned])
        with pytest.raises(LinearAPIError, match="Authentication failed"):
            client.list_experiments()

    def test_api_error_with_multiple_errors(self):
        canned = {
            "errors": [
                {"message": "Error one"},
                {"message": "Error two"},
            ]
        }
        client, transport = _make_client(responses=[canned])
        with pytest.raises(LinearAPIError):
            client.create_experiment_issue("Title", "Desc")

    def test_canceled_state_in_state_ids(self):
        """Canceled state is available for archiving junk issues."""
        assert "Canceled" in STATE_IDS
        assert STATE_IDS["Canceled"]  # non-empty string

    def test_update_to_canceled_state(self):
        """Can transition an issue to Canceled state."""
        canned = {"data": {"issueUpdate": {"success": True}}}
        client, transport = _make_client(responses=[canned])
        client.update_experiment_status("issue-junk", "Canceled")

        body = json.loads(transport.requests[0].content)
        assert body["variables"]["input"]["stateId"] == STATE_IDS["Canceled"]

    def test_content_type_header_is_json(self):
        canned = {
            "data": {
                "issueCreate": {
                    "success": True,
                    "issue": {"id": "issue-1"},
                }
            }
        }
        client, transport = _make_client(responses=[canned])
        client.create_experiment_issue("Title", "Desc")

        req = transport.requests[0]
        assert req.headers["content-type"] == "application/json"


# --- format_experiment_description ---


class TestFormatExperimentDescription:
    """LinearClient.format_experiment_description produces markdown from config."""

    @pytest.fixture
    def config(self):
        """Build a minimal ExperimentConfig for description formatting tests."""
        from scaffold.config import (
            ExperimentConfig,
            GateConfig,
            HypothesesConfig,
            ModelConfig,
            ModelsConfig,
            NullModelConfig,
            PhaseConfig,
            RuntimeConfig,
        )
        return ExperimentConfig(
            name="test-exp",
            thesis="Transformers contain latent routing.",
            research_question="Does X cause Y?",
            models=ModelsConfig(
                development=ModelConfig(name="gpt2", purpose="fast_iteration"),
                primary=ModelConfig(name="gemma-2-2b", purpose="main_results"),
            ),
            runtime=RuntimeConfig(),
            hypotheses=HypothesesConfig(primary="H1 statement"),
            null_models=[
                NullModelConfig(name="uniform", description="Equal weight to all layers"),
                NullModelConfig(name="random_dirichlet", description="Random Dirichlet"),
            ],
            phases=[
                PhaseConfig(
                    name="phase1_oracle",
                    description="Compute oracle weights",
                    gates=[
                        GateConfig(metric="cross_entropy_delta", threshold=0.01, comparator="gte"),
                        GateConfig(metric="p_value", threshold=0.01, comparator="lte"),
                    ],
                    phase_type="pilot",
                ),
                PhaseConfig(
                    name="phase2_patterns",
                    description="Analyze routing patterns",
                    gates=[
                        GateConfig(metric="silhouette_score", threshold=0.2, comparator="gte"),
                    ],
                    requires_human_review=True,
                    depends_on=["phase1_oracle"],
                    phase_type="confirm",
                ),
            ],
            required_lanes=["oracle_alpha", "patterns"],
            statistics={"clustering_distance": "jsd"},
            framing_locks=["non-causal language"],
            guardrails=["no causation"],
        )

    def test_contains_research_question(self, config):
        result = LinearClient.format_experiment_description(config)
        assert "Does X cause Y?" in result

    def test_contains_thesis(self, config):
        result = LinearClient.format_experiment_description(config)
        assert "Transformers contain latent routing." in result

    def test_contains_phase_names(self, config):
        result = LinearClient.format_experiment_description(config)
        assert "phase1_oracle" in result
        assert "phase2_patterns" in result

    def test_contains_gate_thresholds(self, config):
        result = LinearClient.format_experiment_description(config)
        assert ">= 0.01" in result
        assert "<= 0.01" in result
        assert ">= 0.2" in result

    def test_contains_model_names(self, config):
        result = LinearClient.format_experiment_description(config)
        assert "gpt2" in result
        assert "gemma-2-2b" in result

    def test_contains_null_models(self, config):
        result = LinearClient.format_experiment_description(config)
        assert "uniform" in result
        assert "random_dirichlet" in result

    def test_handles_no_null_models(self, config):
        config.null_models = []
        result = LinearClient.format_experiment_description(config)
        assert "Research Question" in result
        assert "Null Models" not in result

    def test_handles_secondary_model(self, config):
        from scaffold.config import ModelConfig
        config.models.secondary = ModelConfig(name="llama-3", purpose="cross_validation")
        result = LinearClient.format_experiment_description(config)
        assert "llama-3" in result
        assert "cross_validation" in result

    def test_contains_phase_type_labels(self, config):
        result = LinearClient.format_experiment_description(config)
        assert "[pilot]" in result
        assert "[confirm]" in result

    def test_contains_depends_on(self, config):
        result = LinearClient.format_experiment_description(config)
        assert "phase1_oracle" in result  # in depends_on for phase2

    def test_contains_human_review_note(self, config):
        result = LinearClient.format_experiment_description(config)
        assert "human review" in result.lower()

    def test_returns_string(self, config):
        result = LinearClient.format_experiment_description(config)
        assert isinstance(result, str)
        assert len(result) > 0


# --- add_phase_comment with phase_states ---


class TestAddPhaseCommentWithPhaseStates:
    """add_phase_comment includes experiment progress when phase_states provided."""

    def test_phase_states_included_in_comment(self):
        canned = {"data": {"commentCreate": {"success": True}}}
        client, transport = _make_client(responses=[canned])

        gate_report = {
            "overall_pass": True,
            "results": [
                {
                    "metric": "accuracy",
                    "status": "PASS",
                    "observed_value": 0.95,
                    "threshold": 0.90,
                    "comparator": "gte",
                },
            ],
        }
        phase_states = [
            {"name": "phase1_oracle", "status": "COMPLETED"},
            {"name": "phase2_patterns", "status": "IN_PROGRESS"},
            {"name": "phase3_writeup", "status": "NOT_STARTED"},
        ]
        client.add_phase_comment(
            "issue-42", "phase2_patterns", gate_report,
            phase_states=phase_states,
        )

        body = json.loads(transport.requests[0].content)
        comment_body = body["variables"]["input"]["body"]
        assert "Experiment Progress" in comment_body
        assert "phase1_oracle" in comment_body
        assert "COMPLETED" in comment_body
        assert "phase2_patterns" in comment_body
        assert "IN_PROGRESS" in comment_body
        assert "phase3_writeup" in comment_body
        assert "NOT_STARTED" in comment_body

    def test_no_phase_states_no_progress_section(self):
        canned = {"data": {"commentCreate": {"success": True}}}
        client, transport = _make_client(responses=[canned])

        gate_report = {
            "overall_pass": True,
            "results": [
                {
                    "metric": "accuracy",
                    "status": "PASS",
                    "observed_value": 0.95,
                    "threshold": 0.90,
                    "comparator": "gte",
                },
            ],
        }
        client.add_phase_comment("issue-42", "phase1", gate_report)

        body = json.loads(transport.requests[0].content)
        comment_body = body["variables"]["input"]["body"]
        assert "Experiment Progress" not in comment_body

    def test_phase_states_shows_status_icons(self):
        canned = {"data": {"commentCreate": {"success": True}}}
        client, transport = _make_client(responses=[canned])

        gate_report = {
            "overall_pass": False,
            "results": [
                {
                    "metric": "accuracy",
                    "status": "FAIL",
                    "observed_value": 0.50,
                    "threshold": 0.90,
                    "comparator": "gte",
                },
            ],
        }
        phase_states = [
            {"name": "phase1", "status": "COMPLETED"},
            {"name": "phase2", "status": "GATE_CHECK"},
            {"name": "phase3", "status": "GATE_FAILED"},
            {"name": "phase4", "status": "NOT_STARTED"},
        ]
        client.add_phase_comment(
            "issue-42", "phase2", gate_report,
            phase_states=phase_states,
        )

        body = json.loads(transport.requests[0].content)
        comment_body = body["variables"]["input"]["body"]
        assert "[done]" in comment_body
        assert "[current]" in comment_body
        assert "[retry]" in comment_body
        assert "[pending]" in comment_body
