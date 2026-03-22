# ABOUTME: Loads WORKFLOW.md files using the Symphony pattern: YAML frontmatter + Markdown prompt body.
# ABOUTME: Parses frontmatter into WorkflowConfig sections and renders prompt templates via Jinja2.

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml
from jinja2 import BaseLoader, Environment, Undefined


class _SilentUndefined(Undefined):
    """Jinja2 Undefined subclass that renders as empty string instead of raising."""

    def __str__(self) -> str:
        return ""

    def __iter__(self):
        return iter([])

    def __bool__(self) -> bool:
        return False


@dataclass
class WorkflowConfig:
    """Parsed WORKFLOW.md with separated frontmatter sections and prompt template."""

    runtime: dict = field(default_factory=dict)
    agent: dict = field(default_factory=dict)
    hooks: dict = field(default_factory=dict)
    prompt_template: str = ""


def load_workflow(path: Path) -> WorkflowConfig:
    """Load a WORKFLOW.md file, parsing YAML frontmatter and prompt body.

    Format:
    ---
    yaml: frontmatter
    ---

    Markdown prompt body with {{ jinja2 }} variables

    Raises ValueError if file has no valid frontmatter.
    """
    text = path.read_text()

    # Must start with --- delimiter
    if not text.startswith("---"):
        raise ValueError(f"No valid frontmatter found in {path}: file must start with '---'")

    # Find the closing --- delimiter
    second_marker = text.find("---", 3)
    if second_marker == -1:
        raise ValueError(f"No valid frontmatter found in {path}: missing closing '---' delimiter")

    frontmatter_text = text[3:second_marker].strip()
    body = text[second_marker + 3:].lstrip("\n")

    # Parse YAML frontmatter
    if frontmatter_text:
        parsed = yaml.safe_load(frontmatter_text)
        if parsed is None:
            parsed = {}
    else:
        parsed = {}

    return WorkflowConfig(
        runtime=parsed.get("runtime", {}) or {},
        agent=parsed.get("agent", {}) or {},
        hooks=parsed.get("hooks", {}) or {},
        prompt_template=body,
    )


def render_prompt(workflow: WorkflowConfig, context: dict) -> str:
    """Render the prompt template with the given context variables.

    Context typically includes: phase, lane, task.
    Uses Jinja2 to render the template string. Undefined variables render as empty string.
    """
    env = Environment(loader=BaseLoader(), undefined=_SilentUndefined)
    template = env.from_string(workflow.prompt_template)
    return template.render(**context)
