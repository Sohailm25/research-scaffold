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

    def add_phase_comment(
        self, issue_id: str, phase: str, gate_report: dict
    ) -> None:
        """Post phase gate results as a comment on the experiment issue."""
        body = f"## Phase: {phase}\n\n"
        body += f"**Overall:** {'PASS' if gate_report.get('overall_pass') else 'FAIL'}\n\n"
        for result in gate_report.get("results", []):
            body += (
                f"- {result.get('metric', '?')}: {result.get('status', '?')} "
                f"(observed={result.get('observed_value', '?')})\n"
            )

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
