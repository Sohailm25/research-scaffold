# ABOUTME: Document intake module that reads research docs and synthesizes experiment config.
# ABOUTME: Uses claude CLI (OAuth) for LLM synthesis instead of API keys.

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol


class LLMRunner(Protocol):
    """Protocol for LLM execution backends."""

    def run(self, prompt: str) -> str:
        """Send prompt, return response text."""
        ...


class ClaudeCLIRunner:
    """Runs prompts via the claude CLI tool (OAuth authenticated)."""

    def __init__(self, timeout: int = 300):
        self._timeout = timeout

    def run(self, prompt: str) -> str:
        """Send prompt to claude CLI and return response."""
        result = subprocess.run(
            ["claude", "--print", "--dangerously-skip-permissions", "-p", prompt],
            capture_output=True,
            text=True,
            timeout=self._timeout,
        )
        if result.returncode != 0:
            raise RuntimeError(f"claude CLI failed: {result.stderr}")
        return result.stdout.strip()


VALID_EXTENSIONS = frozenset({".md", ".txt", ".pdf", ".docx"})


@dataclass
class IntakeResult:
    """Synthesized experiment configuration from document intake."""

    experiment_name: str
    research_question: str
    hypotheses: dict  # {primary: str, secondary: [str]}
    null_models: list[dict]  # [{name, description}]
    framing_locks: list[str]
    required_lanes: list[str]
    phases: list[dict]  # [{name, description, gates: [{metric, threshold, comparator}]}]
    models: dict  # {development: {name, purpose}, primary: {name, purpose}}
    guardrails: list[str]
    statistics: dict
    source_documents: list[Path] = field(default_factory=list)

    def to_experiment_config(self) -> "ExperimentConfig":
        """Convert to ExperimentConfig dataclass from scaffold.config."""
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

        models = ModelsConfig(
            development=ModelConfig(
                name=self.models["development"]["name"],
                purpose=self.models["development"]["purpose"],
            ),
            primary=ModelConfig(
                name=self.models["primary"]["name"],
                purpose=self.models["primary"]["purpose"],
            ),
        )

        hypotheses = HypothesesConfig(
            primary=self.hypotheses["primary"],
            secondary=self.hypotheses.get("secondary", []),
        )

        null_models = [
            NullModelConfig(name=nm["name"], description=nm.get("description", ""))
            for nm in self.null_models
        ]

        phases = []
        for p in self.phases:
            gates = [
                GateConfig(
                    metric=g["metric"],
                    threshold=float(g["threshold"]),
                    comparator=g["comparator"],
                )
                for g in p.get("gates", [])
            ]
            phases.append(
                PhaseConfig(
                    name=p["name"],
                    description=p["description"],
                    gates=gates,
                    requires_human_review=p.get("requires_human_review", False),
                    depends_on=p.get("depends_on", []),
                )
            )

        return ExperimentConfig(
            name=self.experiment_name,
            thesis=self.research_question,
            research_question=self.research_question,
            models=models,
            runtime=RuntimeConfig(),
            hypotheses=hypotheses,
            null_models=null_models,
            phases=phases,
            required_lanes=self.required_lanes,
            statistics=self.statistics,
            framing_locks=self.framing_locks,
            guardrails=self.guardrails,
        )


INTAKE_PROMPT = """You are a research experiment designer. Given the following research documents, synthesize a structured experiment configuration.

DOCUMENTS:
{documents}

Respond with ONLY a JSON object (no markdown, no explanation) with these exact fields:

{{
  "experiment_name": "kebab-case-name",
  "research_question": "One sentence research question",
  "hypotheses": {{
    "primary": "Primary hypothesis",
    "secondary": ["Secondary hypothesis 1", "Secondary hypothesis 2"]
  }},
  "null_models": [
    {{"name": "baseline_name", "description": "What it tests"}}
  ],
  "framing_locks": [
    "Epistemic boundary 1 (e.g., This is observational, not causal)"
  ],
  "required_lanes": ["lane1", "lane2"],
  "phases": [
    {{
      "name": "phase_name",
      "description": "What this phase does",
      "gates": [
        {{"metric": "metric_name", "threshold": 0.05, "comparator": "lte"}}
      ],
      "requires_human_review": false,
      "depends_on": []
    }}
  ],
  "models": {{
    "development": {{"name": "model-id", "purpose": "fast iteration"}},
    "primary": {{"name": "model-id", "purpose": "main results"}}
  }},
  "guardrails": ["Guardrail 1"],
  "statistics": {{
    "significance_level": 0.05,
    "effect_size_minimum": 0.2
  }}
}}

Requirements:
- experiment_name must be kebab-case
- Include at least one null model
- Include at least one framing lock preventing overclaiming
- Phase gates must have quantitative thresholds
- Use pilot/confirmatory split by default (Phase 1 pilot, Phase 2 confirmatory)
"""


def scan_documents(docs_dir: Path) -> list[Path]:
    """Find all readable documents in a directory (non-recursive)."""
    docs = []
    for path in sorted(docs_dir.iterdir()):
        if path.is_file() and path.suffix.lower() in VALID_EXTENSIONS:
            docs.append(path)
    return docs


def read_document(path: Path) -> str:
    """Read text content from a document file."""
    suffix = path.suffix.lower()
    if suffix in (".md", ".txt"):
        return path.read_text()
    elif suffix == ".pdf":
        try:
            import fitz  # pymupdf

            doc = fitz.open(str(path))
            text = ""
            for page in doc:
                text += page.get_text()
            doc.close()
            return text if text else f"[PDF file: {path.name} - no extractable text]"
        except ImportError:
            return f"[PDF file: {path.name} - install pymupdf for text extraction]"
        except Exception:
            return f"[PDF file: {path.name} - could not extract text]"
    elif suffix == ".docx":
        return f"[DOCX file: {path.name} - docx support not yet implemented]"
    return ""


def synthesize_config(documents: dict[str, str], runner: LLMRunner) -> IntakeResult:
    """Send documents to LLM and parse the response into IntakeResult."""
    doc_parts = []
    for name, content in documents.items():
        doc_parts.append(f"--- {name} ---\n{content}\n")
    docs_text = "\n".join(doc_parts)

    prompt = INTAKE_PROMPT.format(documents=docs_text)
    response = runner.run(prompt)

    # Parse JSON from response, stripping any markdown fencing
    json_text = response.strip()
    if json_text.startswith("```"):
        lines = json_text.split("\n")
        lines = [line for line in lines if not line.strip().startswith("```")]
        json_text = "\n".join(lines)

    data = json.loads(json_text)

    return IntakeResult(
        experiment_name=data["experiment_name"],
        research_question=data["research_question"],
        hypotheses=data["hypotheses"],
        null_models=data["null_models"],
        framing_locks=data["framing_locks"],
        required_lanes=data["required_lanes"],
        phases=data["phases"],
        models=data["models"],
        guardrails=data["guardrails"],
        statistics=data.get("statistics", {}),
    )


def intake(docs_dir: Path, runner: LLMRunner | None = None) -> IntakeResult:
    """Full intake pipeline: scan documents, read them, synthesize config.

    If docs_dir contains IDEA.md, it gets priority positioning in the prompt.
    """
    if runner is None:
        runner = ClaudeCLIRunner()

    paths = scan_documents(docs_dir)
    if not paths:
        raise ValueError(f"No documents found in {docs_dir}")

    # Read all documents, with IDEA.md first if present
    documents: dict[str, str] = {}
    idea_path = docs_dir / "IDEA.md"
    if idea_path.exists():
        documents["IDEA.md (PRIMARY - this is the user's explicit research intent)"] = (
            idea_path.read_text()
        )

    for path in paths:
        if path.name == "IDEA.md":
            continue  # already added with priority marker
        documents[path.name] = read_document(path)

    result = synthesize_config(documents, runner)
    result.source_documents = paths
    return result
