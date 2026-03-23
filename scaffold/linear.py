# ABOUTME: Linear GraphQL adapter for experiment portfolio tracking.
# ABOUTME: Each experiment is a Linear issue on the Experiments project board.

from __future__ import annotations

from pathlib import Path

import httpx
import yaml

LINEAR_API_URL = "https://api.linear.app/graphql"

# Workflow state IDs for the SOH team
STATE_IDS = {
    "Todo": "0a618e42-6cdd-4872-8a05-23b64dc1e03c",
    "In Progress": "a9938f4d-99c0-4619-b894-e4df378ae901",
    "In Review": "ce1c1340-d5a5-4a0e-b519-0b0a47cf119d",
    "Done": "41170148-524f-46b8-b65e-eb8e6d5bb969",
    "Canceled": "fef63550-b7df-40d3-9110-09723bfffc18",
}

# Default IDs
DEFAULT_TEAM_ID = "d5c8cdf1-1a11-4f96-ac38-0036175eafb5"
DEFAULT_PROJECT_ID = "8ee9986b-eae0-4cee-9688-08259daeac73"


class LinearAPIError(Exception):
    """Raised when a Linear API call fails."""


def load_scaffold_config() -> dict:
    """Load ~/.scaffold/config.yaml and return as dict."""
    config_path = Path.home() / ".scaffold" / "config.yaml"
    if not config_path.exists():
        raise FileNotFoundError(f"Scaffold config not found: {config_path}")
    with open(config_path) as f:
        return yaml.safe_load(f) or {}


class LinearClient:
    """Client for Linear GraphQL API."""

    def __init__(
        self,
        api_key: str | None = None,
        team_id: str = DEFAULT_TEAM_ID,
        project_id: str = DEFAULT_PROJECT_ID,
        client: httpx.Client | None = None,
    ):
        if api_key is None:
            config = load_scaffold_config()
            api_key = config.get("linear_api_key")
            if not api_key:
                raise ValueError("No Linear API key found in config or parameter")

        self._api_key = api_key
        self._team_id = team_id
        self._project_id = project_id
        self._client = client or httpx.Client()

    def _query(self, query: str, variables: dict | None = None) -> dict:
        """Execute a GraphQL query/mutation."""
        payload: dict = {"query": query}
        if variables:
            payload["variables"] = variables

        response = self._client.post(
            LINEAR_API_URL,
            json=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": self._api_key,
            },
        )

        data = response.json()
        if "errors" in data:
            raise LinearAPIError(f"Linear API error: {data['errors']}")
        return data.get("data", {})

    def create_experiment_issue(self, title: str, description: str) -> str:
        """Create a Linear issue for a new experiment. Returns issue ID."""
        mutation = """
        mutation CreateIssue($input: IssueCreateInput!) {
            issueCreate(input: $input) {
                success
                issue { id }
            }
        }
        """
        variables = {
            "input": {
                "title": title,
                "description": description,
                "teamId": self._team_id,
                "projectId": self._project_id,
                "stateId": STATE_IDS["Todo"],
            }
        }
        data = self._query(mutation, variables)
        result = data.get("issueCreate", {})
        if not result.get("success"):
            raise LinearAPIError("Failed to create issue")
        return result["issue"]["id"]

    def update_experiment_status(self, issue_id: str, state_name: str) -> None:
        """Update experiment status. state_name: Todo / In Progress / In Review / Done."""
        state_id = STATE_IDS.get(state_name)
        if not state_id:
            raise ValueError(
                f"Unknown state: {state_name}. Valid: {list(STATE_IDS.keys())}"
            )

        mutation = """
        mutation UpdateIssue($id: String!, $input: IssueUpdateInput!) {
            issueUpdate(id: $id, input: $input) {
                success
            }
        }
        """
        variables = {
            "id": issue_id,
            "input": {"stateId": state_id},
        }
        data = self._query(mutation, variables)
        if not data.get("issueUpdate", {}).get("success"):
            raise LinearAPIError(f"Failed to update issue {issue_id}")

    _COMPARATOR_SYMBOLS = {
        "gte": ">=",
        "lte": "<=",
        "gt": ">",
        "lt": "<",
        "eq": "=",
    }

    @staticmethod
    def format_experiment_description(config) -> str:
        """Build a human-readable Linear issue description from experiment config."""
        lines = []

        # Research question
        lines.append("## Research Question\n")
        lines.append(f"{config.research_question}\n")

        # Thesis
        lines.append("## Thesis\n")
        lines.append(f"{config.thesis}\n")

        # Models
        lines.append("## Models\n")
        lines.append(f"- **Primary:** {config.models.primary.name} ({config.models.primary.purpose})")
        lines.append(f"- **Development:** {config.models.development.name} ({config.models.development.purpose})")
        if config.models.secondary:
            lines.append(f"- **Secondary:** {config.models.secondary.name} ({config.models.secondary.purpose})")
        lines.append("")

        # Phase roadmap
        lines.append("## Phase Roadmap\n")
        for i, phase in enumerate(config.phases, 1):
            phase_type_label = f" [{phase.phase_type}]" if phase.phase_type else ""
            lines.append(f"### {i}. {phase.name}{phase_type_label}\n")
            lines.append(f"{phase.description}\n")
            if phase.gates:
                lines.append("**Gates:**")
                for g in phase.gates:
                    symbol = LinearClient._COMPARATOR_SYMBOLS.get(g.comparator, g.comparator)
                    lines.append(f"- `{g.metric}` {symbol} {g.threshold}")
                lines.append("")
            if phase.requires_human_review:
                lines.append("*Requires human review before advancing.*\n")
            if phase.depends_on:
                lines.append(f"*Depends on:* {', '.join(phase.depends_on)}\n")

        # Null models
        if config.null_models:
            lines.append("## Null Models\n")
            for nm in config.null_models:
                desc = f" -- {nm.description}" if nm.description else ""
                lines.append(f"- **{nm.name}**{desc}")
            lines.append("")

        return "\n".join(lines)

    def add_phase_comment(
        self,
        issue_id: str,
        phase: str,
        gate_report: dict,
        iteration: int | None = None,
        max_iterations: int | None = None,
        phase_states: list[dict] | None = None,
    ) -> None:
        """Post phase gate results as a comment on the experiment issue."""
        results = gate_report.get("results", [])
        overall_pass = gate_report.get("overall_pass", False)
        total = len(results)
        all_skip = total > 0 and all(r.get("status") == "SKIP" for r in results)
        fail_count = sum(1 for r in results if r.get("status") == "FAIL")

        # Header line
        if overall_pass:
            iter_suffix = f" (iteration {iteration})" if iteration is not None else ""
            body = f"## Phase: {phase} -- PASSED{iter_suffix}\n\n"
        elif all_skip:
            iter_suffix = ""
            if iteration is not None and max_iterations is not None:
                iter_suffix = f" -- Iteration {iteration}/{max_iterations}"
            elif iteration is not None:
                iter_suffix = f" -- Iteration {iteration}"
            body = f"## Phase: {phase}{iter_suffix}\n\n"
        else:
            iter_suffix = ""
            if iteration is not None and max_iterations is not None:
                iter_suffix = f" -- Iteration {iteration}/{max_iterations}"
            elif iteration is not None:
                iter_suffix = f" -- Iteration {iteration}"
            body = f"## Phase: {phase}{iter_suffix}\n\n"

        # Result summary
        if overall_pass:
            body += f"All {total} gates passed.\n\n"
        elif all_skip:
            body += f"**Result: NO METRICS** (agent produced no result.json)\n\n"
            body += f"All {total} gates evaluated as SKIP -- the agent did not produce any metrics this iteration.\n\n"
        else:
            body += f"**Result: FAIL** ({fail_count} of {total} gates failed)\n\n"

        # Table (only for non-all-skip scenarios)
        if not all_skip and total > 0:
            body += "| Gate | Threshold | Observed | Status |\n"
            body += "|------|-----------|----------|--------|\n"
            for r in results:
                metric = r.get("metric", "?")
                status = r.get("status", "?")
                observed = r.get("observed_value")
                threshold = r.get("threshold")
                comparator = r.get("comparator", "")
                symbol = self._COMPARATOR_SYMBOLS.get(comparator, comparator)
                threshold_str = f"{symbol} {threshold}" if threshold is not None else "?"
                observed_str = str(observed) if observed is not None else "N/A"
                body += f"| {metric} | {threshold_str} | {observed_str} | {status} |\n"
            body += "\n"

        # Footer
        if overall_pass:
            body += "*Status: Awaiting human review before advancing.*\n"
        elif all_skip:
            body += "*Next: Orchestrator will retry. Aborts after 3 consecutive agent failures.*\n"
        else:
            body += "*Next: Orchestrator will retry with feedback about what failed.*\n"

        if phase_states:
            body += "\n---\n\n### Experiment Progress\n\n"
            for ps in phase_states:
                status = ps.get("status", "NOT_STARTED")
                name = ps.get("name", "?")
                if status == "COMPLETED":
                    icon = "done"
                elif status in ("IN_PROGRESS", "GATE_CHECK"):
                    icon = "current"
                elif status == "GATE_FAILED":
                    icon = "retry"
                else:
                    icon = "pending"
                body += f"- [{icon}] {name}: {status}\n"

        mutation = """
        mutation CreateComment($input: CommentCreateInput!) {
            commentCreate(input: $input) {
                success
            }
        }
        """
        variables = {
            "input": {
                "issueId": issue_id,
                "body": body,
            }
        }
        data = self._query(mutation, variables)
        if not data.get("commentCreate", {}).get("success"):
            raise LinearAPIError(f"Failed to add comment to issue {issue_id}")

    def list_experiments(self) -> list[dict]:
        """Fetch all experiment issues from the project board."""
        query = """
        query ListExperiments($projectId: String!) {
            project(id: $projectId) {
                issues {
                    nodes {
                        id
                        title
                        description
                        state { name type }
                        createdAt
                        updatedAt
                    }
                }
            }
        }
        """
        variables = {"projectId": self._project_id}
        data = self._query(query, variables)
        project = data.get("project", {})
        issues = project.get("issues", {}).get("nodes", [])
        return [
            {
                "id": issue["id"],
                "title": issue["title"],
                "description": issue.get("description", ""),
                "state": issue.get("state", {}).get("name", ""),
                "created_at": issue.get("createdAt", ""),
                "updated_at": issue.get("updatedAt", ""),
            }
            for issue in issues
        ]

    def find_experiment_issue(self, title: str) -> str | None:
        """Find existing experiment issue by title. Returns issue ID or None."""
        experiments = self.list_experiments()
        for exp in experiments:
            if exp["title"] == title:
                return exp["id"]
        return None
